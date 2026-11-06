import httpx
import pytest
from scientific_dss_kag.connectors import CatalogClient


def test_catalog_contract_read_only():
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json=[{'id':'urn:model:1','label':'model'}])
    client=CatalogClient('https://catalog.example/api',transport=httpx.MockTransport(handler))
    assert client.list_resources('models','MaxEnt')['records'][0]['id']=='urn:model:1'
    client.list_resources('standardvariables')
    assert seen[0].url.path=='/api/models'
    assert seen[1].url.path=='/api/standardvariables'
    assert all(r.method=='GET' for r in seen)
    assert seen[0].url.params['per_page']=='100'
    with pytest.raises(ValueError): client.list_resources('../executions')
    client.close()


@pytest.mark.parametrize('url',['http://example.com','https://user:secret@example.com','file:///etc/passwd','https://example.com?token=x'])
def test_url_validation(url):
    with pytest.raises(ValueError): CatalogClient(url)


def test_errors_not_silent_fallback():
    client=CatalogClient('https://example.com',transport=httpx.MockTransport(lambda r:httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError): client.list_resources('models')
    client.close()
    client=CatalogClient('https://example.com',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'items':[]})))
    with pytest.raises(ValueError): client.list_resources('models')
    client.close()


def test_timeout():
    def timeout(request): raise httpx.ReadTimeout('timeout',request=request)
    client=CatalogClient('https://example.com',transport=httpx.MockTransport(timeout))
    with pytest.raises(httpx.ReadTimeout): client.list_resources('models')
    client.close()
