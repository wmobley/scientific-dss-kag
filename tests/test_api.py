import pytest
from fastapi.testclient import TestClient
from scientific_dss_kag.api import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.mark.parametrize('path',['/health','/integrations','/catalog/models','/catalog/variables','/','/workbench.js','/workbench.css'])
def test_routes(client,path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['x-content-type-options'] == 'nosniff'


@pytest.mark.parametrize('mode',['lexical','hybrid','ontology'])
def test_retrieval_modes(client,mode):
    response = client.post('/retrieve',json={'query':'spatial validation','mode':mode,'context':['ValidationActivity']})
    assert response.status_code == 200
    assert response.json()['synthetic'] is True
    assert response.json()['results']


@pytest.mark.parametrize('payload',[{'query':''},{'query':'   '},{'query':'x','k':0},{'query':'x','k':21},{'query':'x','mode':'fake'},{'query':'x','context':['fake']},{'query':'x','url':'https://example.com'},{'query':'x','mode':'ontology'}])
def test_invalid_inputs(client,payload):
    assert client.post('/retrieve',json=payload).status_code == 422


def test_kag_unavailable_and_catalog_honesty(client):
    response = client.post('/retrieve',json={'query':'x','mode':'kag'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'integration_unavailable'
    assert all(v['live_verified'] is False for v in client.get('/integrations').json().values())
    assert client.get('/catalog/models').json()['origin'] == 'synthetic_fixture'


def test_pathway_gaps_and_candidate(client):
    assert not client.post('/validate/pathway',json={}).json()['structurally_complete']
    pathway = dict(objective='surveillance',information_needs=['observations'],alternatives=['MaxEnt'],uncertainties=['bias'],evidence_ids=['ev-sampling'])
    result = client.post('/validate/pathway',json=pathway).json()
    assert result['structurally_complete'] and result['scientifically_validated'] is False
    pathway['evidence_ids']=['ev-candidate']
    assert client.post('/validate/pathway',json=pathway).json()['invalid_or_unreviewed_evidence'] == ['ev-candidate']


def test_evaluation_and_bounds(client):
    assert len(client.post('/evaluate',json={'k':3}).json()['rows']) == 12
    assert client.post('/evaluate',json={'k':100}).status_code == 422
    assert client.post('/retrieve',content='x'*70000).status_code == 413


def test_streamed_body_limit(client):
    response=client.post('/retrieve',content=iter([b'{"query":"x","padding":"',b'x'*70000,b'"}']),headers={'content-type':'application/json'})
    assert response.status_code == 413


def test_docs_csp_nonce_and_schema(client):
    import re
    response=client.get('/docs')
    nonce=re.search(r'<script nonce="([^"]+)"',response.text).group(1)
    assert f"'nonce-{nonce}'" in response.headers['content-security-policy']
    assert 'https://cdn.jsdelivr.net' in response.headers['content-security-policy']
    assert 'cdn.jsdelivr.net' not in client.get('/').headers['content-security-policy']
    assert '/retrieve' in client.get('/openapi.json').json()['paths']
