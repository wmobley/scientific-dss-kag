"""OpenAI contract tests use synthetic data + MockTransport, never paid calls."""
import json
from copy import deepcopy
import httpx
import pytest
from fastapi.testclient import TestClient
from scientific_dss_kag.api import create_app
from scientific_dss_kag.models import RetrievalRequest
from scientific_dss_kag.openai_provider import OpenAIProvider, ProviderError
from scientific_dss_kag.retrieval import Retriever
from scientific_dss_kag.settings import OpenAISettings

KEY = 'test-key-never-a-real-credential'


def complete(answer=None):
    answer = answer if answer is not None else {'status':'answered','claims':[{'text':'Background selection affects interpretation.','evidence_ids':['ev-maxent']}],'gaps':[],'uncertainties':['Synthetic teaching notes.']}
    return {'id':'resp_test','model':'gpt-4.1-mini-2025-04-14','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(answer)}]}], 'usage':{'input_tokens':20,'output_tokens':30,'total_tokens':50}}


def handler_for(calls, response=None, mutate_embedding=None):
    def handler(request):
        body=json.loads(request.content);calls.append((request,body))
        assert request.url.host == 'api.openai.com'
        assert request.headers['authorization'] == 'Bearer '+KEY
        if request.url.path == '/v1/embeddings':
            rows=[{'index':i,'embedding':[1.0,float(i+1),.5]} for i in range(len(body['input']))]
            data={'data':list(reversed(rows)),'model':body['model'],'usage':{'prompt_tokens':10,'total_tokens':10}}
            if mutate_embedding: mutate_embedding(data)
            return httpx.Response(200,json=data)
        assert request.url.path == '/v1/responses'
        return httpx.Response(200,json=response if response is not None else complete())
    return handler


def provider(calls=None, response=None, mutate_embedding=None):
    calls=calls if calls is not None else []
    return OpenAIProvider(OpenAISettings(enabled=True,api_key=KEY),httpx.MockTransport(handler_for(calls,response,mutate_embedding)))


def retrieved():
    return Retriever().retrieve(RetrievalRequest(query='MaxEnt background assumptions',mode='ontology',context=['ScientificMethod']))


def test_no_startup_calls_and_offline_defaults():
    calls=[];p=provider(calls)
    with TestClient(create_app(provider=p)) as client:
        assert not calls
        assert client.post('/retrieve',json={'query':'spatial'}).status_code==200
        assert not calls
        assert KEY not in client.get('/integrations').text
        assert 'test-key' not in repr(p.settings)


def test_disabled_and_missing_key():
    for settings in [OpenAISettings(),OpenAISettings(enabled=True)]:
        with TestClient(create_app(settings=settings),base_url='http://127.0.0.1:8091') as client:
            for path,payload in [('/answer',{'query':'habitat'}),('/retrieve',{'query':'habitat','backend':'openai'})]:
                assert client.post(path,json=payload).status_code==503


def test_embeddings_cache_usage_order_and_candidates():
    calls=[];p=provider(calls);r=Retriever()
    request=RetrievalRequest(query='habitat',backend='openai')
    with p.operation():
        first=r.retrieve(request,p);second=r.retrieve(request,p)
    assert len(calls)==3 # one corpus + two queries
    assert len(calls[0][1]['input'])==4
    assert not any('deliberately unsupported' in s for s in calls[0][1]['input'])
    assert first['results']==second['results']
    assert len(first['embedding_usage'])==2 and len(second['embedding_usage'])==1
    assert 'openai:text-embedding-3-small' in first['method']
    assert p.status()['embeddings_verified'] and not p.status()['live_verified']
    p.close()


def test_cache_invalidates_on_model_and_corpus():
    calls=[];p=provider(calls);r=Retriever();reviewed=[e for e in r.evidence if e.review_status=='reviewed']
    with p.operation():
        p.embedding_scores('x',reviewed,'one');p.embedding_scores('x',reviewed,'two')
        p.settings=OpenAISettings(enabled=True,api_key=KEY,embedding_model='text-embedding-3-large')
        p.embedding_scores('x',reviewed,'two')
    assert len(calls)==6 and len(p._cache)==2
    p.close()


@pytest.mark.parametrize('mutation',[
 lambda d:d['data'].pop(),
 lambda d:d['data'].__setitem__(0,{'index':0,'embedding':[1,2,3]}),
 lambda d:d['data'][0].__setitem__('embedding',[0,0,0]),
 lambda d:d['data'][0].__setitem__('embedding',[1,True,2]),
 lambda d:d['data'][0].__setitem__('embedding',[1,'bad',2]),
 lambda d:d['data'][0].__setitem__('embedding',[1,2]),
 lambda d:d.__setitem__('model','unexpected-model')])
def test_invalid_embeddings_fail_atomically(mutation):
    p=provider(mutate_embedding=mutation)
    with p.operation(),pytest.raises(ProviderError):
        Retriever().retrieve(RetrievalRequest(query='x',backend='openai'),p)
    assert not p._cache
    p.close()


def test_answer_wire_schema_and_citations():
    calls=[];p=provider(calls)
    with p.operation(): answer=p.answer('What affects MaxEnt?',retrieved())
    request,body=calls[0]
    assert body['store'] is False and body['max_output_tokens']==1200
    assert body['text']['format']['type']=='json_schema' and body['text']['format']['strict'] is True
    assert body['text']['format']['schema']['properties']['claims']['items']['properties']['evidence_ids']['items']['enum']==['ev-maxent']
    assert 'tools' not in body
    assert answer['citations'][0]['evidence']['id']=='ev-maxent'
    assert answer['scientifically_validated'] is False
    assert answer['usage']['total_tokens']==50
    p.close()


@pytest.mark.parametrize('answer',[
 {'status':'answered','claims':[],'gaps':[],'uncertainties':[]},
 {'status':'answered','claims':[{'text':'claim','evidence_ids':['ev-sampling']}],'gaps':[],'uncertainties':[]},
 {'status':'answered','claims':[{'text':'claim','evidence_ids':[]}],'gaps':[],'uncertainties':[]},
 {'status':'answered','claims':[{'text':'   ','evidence_ids':['ev-maxent']}],'gaps':[],'uncertainties':[]},
 {'status':'abstained','claims':[{'text':'claim','evidence_ids':['ev-maxent']}],'gaps':[],'uncertainties':[]},
 {'status':'answered','claims':[{'text':'claim','evidence_ids':['ev-maxent']}],'gaps':['x'*501],'uncertainties':[]},
])
def test_invalid_claims_and_unretrieved_citations(answer):
    p=provider(response=complete(answer))
    with p.operation(),pytest.raises(ProviderError,match='malformed claims'):
        p.answer('x',retrieved())
    assert not p.responses_verified
    p.close()


@pytest.mark.parametrize('response,code',[
 ({'status':'incomplete'},'openai_incomplete'),
 ({'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':KEY}]}]},'openai_refusal'),
 ({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'not json'}]}]},'openai_invalid_answer'),
 ({'status':'completed','output':[]},'openai_invalid_answer'),
])
def test_refusal_truncation_malformed(response,code):
    p=provider(response=response)
    with p.operation(),pytest.raises(ProviderError) as exc:p.answer('x',retrieved())
    assert exc.value.code==code and KEY not in str(exc.value)
    p.close()


def test_empty_evidence_abstains_without_generation():
    calls=[];p=provider(calls);r=Retriever().retrieve(RetrievalRequest(query='zzzzzz',mode='lexical'))
    with p.operation():answer=p.answer('zzzzzz',r)
    assert answer['status']=='abstained' and not calls


def test_oversized_context_rejected_before_generation():
    calls=[];p=provider(calls);r=retrieved()
    r['results'][0]['evidence']['passage']='x'*24001
    with p.operation(),pytest.raises(ProviderError) as exc:p.answer('x',r)
    assert exc.value.status==422 and not calls


@pytest.mark.parametrize('status',[302,401,429,500])
def test_no_retry_no_error_body_leak(status):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json={'error':KEY},headers={'Location':'https://evil.example/'})
    p=OpenAIProvider(OpenAISettings(enabled=True,api_key=KEY),httpx.MockTransport(handler))
    with p.operation(),pytest.raises(ProviderError) as exc:p.answer('x',retrieved())
    assert len(calls)==1 and p.calls==1 and KEY not in str(exc.value)
    p.close()


def test_timeout_and_budget_and_concurrency():
    def handler(request):raise httpx.ReadTimeout(KEY,request=request)
    p=OpenAIProvider(OpenAISettings(enabled=True,api_key=KEY),httpx.MockTransport(handler))
    with p.operation():
        with pytest.raises(ProviderError) as exc:p.answer('x',retrieved())
        assert KEY not in str(exc.value)
        with pytest.raises(ProviderError) as busy:
            with p.operation():pass
        assert busy.value.code=='openai_busy'
        p.calls=60
        with pytest.raises(ProviderError) as budget:p.answer('x',retrieved())
        assert budget.value.code=='openai_budget_exhausted'
    p.close()


@pytest.mark.parametrize('origin,fetchsite,host',[
 ('https://evil.example',None,'127.0.0.1:8091'),
 ('null',None,'127.0.0.1:8091'),
 ('http://localhost:9999',None,'localhost:8091'),
 (None,'cross-site','127.0.0.1:8091'),
 ('http://evil.example',None,'evil.example'),
])
def test_paid_route_origin_protection(origin,fetchsite,host):
    calls=[];p=provider(calls);headers={'host':host}
    if origin:headers['origin']=origin
    if fetchsite:headers['sec-fetch-site']=fetchsite
    with TestClient(create_app(provider=p),base_url='http://127.0.0.1:8091') as client:
        for path,payload in [('/answer',{'query':'x'}),('/retrieve',{'query':'x','backend':'openai'})]:
            assert client.post(path,json=payload,headers=headers).status_code==403
    assert not calls


def test_paid_api_success_and_model_not_client_selectable():
    calls=[];p=provider(calls)
    with TestClient(create_app(provider=p),base_url='http://127.0.0.1:8091') as client:
        payload={'query':'MaxEnt','mode':'ontology','context':['ScientificMethod'],'backend':'openai'}
        response=client.post('/answer',json=payload,headers={'origin':'http://127.0.0.1:8091'})
        assert response.status_code==200 and response.json()['provider']=='openai'
        assert client.get('/integrations').json()['openai']['live_verified']
        assert len(calls)==3
        assert client.post('/answer',json={**payload,'model':'injected'}).status_code==422
        assert len(calls)==3


def test_oversized_integer_is_sanitized():
    p=provider(mutate_embedding=lambda d:d['data'][0].__setitem__('embedding',[10**400,1,2]))
    with p.operation(),pytest.raises(ProviderError) as exc:
        Retriever().retrieve(RetrievalRequest(query='x',backend='openai'),p)
    assert exc.value.code=='openai_invalid_embeddings' and not p._cache
    p.close()


def test_query_dimension_mismatch_and_budget_boundary():
    calls=[]
    def change_query(data):
        if len(data['data'])==1:data['data'][0]['embedding']=[1,2]
    p=provider(calls,mutate_embedding=change_query)
    with p.operation(),pytest.raises(ProviderError,match='dimensions differ'):
        Retriever().retrieve(RetrievalRequest(query='x',backend='openai'),p)
    p.close()
    calls=[];p=provider(calls);p.calls=59
    with p.operation(),pytest.raises(ProviderError) as exc:
        Retriever().retrieve(RetrievalRequest(query='x',backend='openai'),p)
    assert exc.value.code=='openai_budget_exhausted' and len(calls)==1 and p.calls==60
    p.close()


def test_multiple_outputs_and_valid_provider_abstention():
    response=complete();response['output'][0]['content']*=2
    p=provider(response=response)
    with p.operation(),pytest.raises(ProviderError) as exc:p.answer('x',retrieved())
    assert exc.value.code=='openai_invalid_answer'
    p.close()
    p=provider(response=complete({'status':'abstained','claims':[],'gaps':['Insufficient evidence for a disease forecast.'],'uncertainties':[]}))
    with p.operation():answer=p.answer('Predict disease incidence',retrieved())
    assert answer['status']=='abstained' and answer['citations']==[]
    p.close()


def test_nonfinite_embedding_is_rejected():
    from scientific_dss_kag.openai_provider import normalized
    for value in [float('inf'),float('nan'),-float('inf')]:
        with pytest.raises(ValueError):normalized([value,1])
