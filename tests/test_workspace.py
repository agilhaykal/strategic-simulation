import copy, json, uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import connectors
from backend.privacy import scrub

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with TestClient(app) as c:yield c

def project(c):
    p=c.post('/api/projects',json={'question':'How will our active financing customers grow next year?','context':'600000 current active customers; Indonesia, cars and motorcycles.'}).json()
    p=c.post(f'/api/projects/{p["id"]}/context-confirmation',json={'revision':p['revision'],'summary':p['context']}).json()
    assert p['context_confirmed'];return p

def upload(c,p,name='portfolio.csv'):
    r=c.post(f'/api/projects/{p["id"]}/sources/csv',files={'file':(name,'month,active_customers,customer_id,email\n2026-01,600000,1234567890123456,person@example.com\n2026-02,610000,1234567890123457,other@example.com\n','text/csv')})
    assert r.status_code==200,r.text
    return r.json()

def select(c,p,s,variable='active_customers'):
    spec={'version':s['version'],'columns':['active_customers'],'mapping':{'active_customers':{'variable':variable,'unit':'customers','definition':'Unique active customers','period':'2026-01 to 2026-02','geography':'Indonesia'}},'aggregation':'last'}
    r=c.put(f'/api/projects/{p["id"]}/sources/{s["id"]}/selection',json=spec);assert r.status_code==200,r.text
    return r.json()

def test_multisource_pii_and_stale_snapshot(client):
    c=client;p=project(c);pid=p['id'];p=upload(c,p);s=p['sources'][-1]
    assert len(s['pii_columns'])==2
    assert 'person@example.com' not in json.dumps(s)
    assert '1234567890123456' not in json.dumps(s)
    assert 'month' in s['columns']
    p=select(c,p,s);s=p['sources'][-1]
    assert s['selected']['variables']['active_customers']['value']==610000
    r=c.post(f'/api/projects/{pid}/sources/{s["id"]}/approve',json={'version':s['version'],'acknowledge':True});assert r.status_code==200
    review=c.get(f'/api/projects/{pid}/evidence-review').json();assert review['ready']
    p=r.json();r=c.post(f'/api/projects/{pid}/evidence-snapshots',json={'revision':p['revision'],'review_hash':review['hash'],'acknowledge':True});assert r.status_code==200,r.text
    snapshot=r.json()['evidence'];assert snapshot['variables']['active_customers']['source_id']==s['id']
    p=upload(c,p,'second.csv')
    assert p['evidence'] is None
    assert p['evidence_snapshots'][0]['hash']==snapshot['hash']
    assert len(p['sources'])==2
    assert c.post(f'/api/projects/{pid}/evidence-snapshots',json={'revision':p['revision'],'review_hash':review['hash'],'acknowledge':True}).status_code!=200

def test_duplicate_mappings_not_silently_merged(client):
    c=client;p=project(c)
    for name in ('one.csv','two.csv'):
        p=upload(c,p,name);s=p['sources'][-1];p=select(c,p,s);s=p['sources'][-1]
        p=c.post(f'/api/projects/{p["id"]}/sources/{s["id"]}/approve',json={'version':s['version'],'acknowledge':True}).json()
    review=c.get(f'/api/projects/{p["id"]}/evidence-review').json()
    assert not review['ready'];assert any('multiple sources' in i for i in review['issues'])

def test_sql_scope_and_aggregate_identifier():
    tables=['public.customers'];columns={'public.customers':['customer_id','balance','month']}
    safe=connectors.validate_sql('SELECT COUNT(DISTINCT customer_id) AS customers FROM public.customers',tables,columns)
    assert 'LIMIT 1001' in safe
    for sql in ['DELETE FROM public.customers','SELECT customer_id FROM public.customers','SELECT * FROM public.customers','SELECT pg_sleep(10) FROM public.customers','SELECT balance FROM private.customers','SELECT balance FROM public.customers; SELECT 1','SELECT balance FROM public.customers FOR UPDATE']:
        with pytest.raises(ValueError):connectors.validate_sql(sql,tables,columns)

def test_chat_retry_and_redaction(client,monkeypatch):
    import backend.main as main
    sent=[]
    class Provider:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kw):
            sent.append(kw['json'])
            return main.httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'reply':'Which horizon should we use?','context_summary':'Financing customers in Indonesia','context_ready':False,'questions':[],'data_requirements':[],'model':None})}}]})
    monkeypatch.setattr(main.httpx,'AsyncClient',Provider)
    monkeypatch.setenv('OPENROUTER_API_KEY','unit-test-key')
    c=client;p=project(c);pid=p['id'];body={'text':'Contact person@example.com, phone +6281234567890','request_id':str(uuid.uuid4()),'outbound_consent':True}
    r=c.post(f'/api/projects/{pid}/messages',json=body);assert r.status_code==200,r.text
    assert 'person@example.com' not in json.dumps(sent)
    assert '+6281234567890' not in json.dumps(sent)
    count=len(r.json()['messages']);assert c.post(f'/api/projects/{pid}/messages',json=body).status_code==200
    assert len(sent)==1
    assert len(c.get(f'/api/projects/{pid}/workspace').json()['messages'])==count

def test_explicit_estimate_snapshot_model_run(client):
    from tests.test_workflow import MODEL
    c=client;p=project(c);pid=p['id']
    p=c.put(f'/api/projects/{pid}/estimates',json={'note':'Demand triangular 80,100,120 and capacity 90, proposed capacity 110; explicit user estimates.'}).json()
    review=c.get(f'/api/projects/{pid}/evidence-review').json();assert review['ready']
    r=c.post(f'/api/projects/{pid}/evidence-snapshots',json={'revision':p['revision'],'review_hash':review['hash'],'acknowledge':True});assert r.status_code==200,r.text
    m=copy.deepcopy(MODEL)
    for v in m['variables']:v['evidence_ref']='estimate:'+v['id']
    assert c.post(f'/api/projects/{pid}/approve',json={'model':m,'acknowledge':True}).status_code==200
    assert c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'estimate-run'}).status_code==200

def test_failed_chat_retry_keeps_one_user_message(client,monkeypatch):
    import backend.main as main
    calls=[]
    class Provider:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kw):
            calls.append(kw)
            if len(calls)==1:return main.httpx.Response(503,json={})
            return main.httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'reply':'Context understood.','questions':[],'model':None})}}]})
    monkeypatch.setattr(main.httpx,'AsyncClient',Provider);monkeypatch.setenv('OPENROUTER_API_KEY','unit-test')
    c=client;p=project(c);pid=p['id'];body={'text':'Use the current 12 month horizon.','request_id':str(uuid.uuid4()),'outbound_consent':True}
    assert c.post(f'/api/projects/{pid}/messages',json=body).status_code==502
    after=c.get(f'/api/projects/{pid}/workspace').json();assert after['messages'][-1]['content']==body['text']
    assert c.post(f'/api/projects/{pid}/messages',json=body).status_code==200
    after=c.get(f'/api/projects/{pid}/workspace').json();assert sum(m.get('request_id')==body['request_id'] and m['role']=='user' for m in after['messages'])==1

def test_uncertain_internet_source_requires_quality_acceptance(client,monkeypatch):
    import backend.connectors as connectors
    monkeypatch.setattr(connectors,'checked_url',lambda u:'research.example.org')
    async def fetch(url):return {'title':'Unverified report','excerpt':'The annual market count was 120 customers in 2025.','trust':'unverified','host':'research.example.org'}
    monkeypatch.setattr(connectors,'fetch_page',fetch)
    c=client;p=project(c);pid=p['id']
    assert c.post(f'/api/projects/{pid}/sources/internet',json={'url':'https://research.example.org/data','access_consent':True}).status_code==422
    r=c.post(f'/api/projects/{pid}/sources/internet',json={'url':'https://research.example.org/data','access_consent':True,'accept_unverified_access':True});assert r.status_code==200
    # Pin a fixture extraction to test the independent source-quality gate.
    import backend.main as main
    p=r.json();s=p['sources'][-1];sid=s['id'];s['suggested_observations']=[{'variable':'market_count','value':120,'quote':'annual market count was 120 customers in 2025','unit':'customers','period':'2025','definition':'Market customers','geography':'Indonesia'}];main.save(p,'fixture')
    r=c.post(f'/api/projects/{pid}/sources/{sid}/observations',json={'version':s['version'],'acknowledge':True});assert r.status_code==200
    s=r.json()['sources'][-1]
    assert c.post(f'/api/projects/{pid}/sources/{sid}/approve',json={'version':s['version'],'acknowledge':True}).status_code==422
    assert c.post(f'/api/projects/{pid}/sources/{sid}/approve',json={'version':s['version'],'acknowledge':True,'accept_uncertainty':True}).status_code==200

def test_url_and_period_privacy_guards(monkeypatch):
    assert scrub('Observation period: 2026-01-01')=='Observation period: 2026-01-01'
    assert '[REDACTED]' in scrub('email person@example.com phone +6281234567890')
    for url in ('http://www.bi.go.id/','https://localhost/','https://user:password@www.bi.go.id/','https://www.bi.go.id:8443/'):
        with pytest.raises(ValueError):connectors.checked_url(url)
    monkeypatch.setattr(connectors.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):connectors.checked_url('https://attacker.example/')

def test_web_text_withheld_until_privacy_review(client,monkeypatch):
    from backend.evidence import agent_sources
    import backend.main as main
    c=client;p=project(c);pid=p['id'];sid=str(uuid.uuid4())
    p['sources']=[{'id':sid,'kind':'internet','label':'Primary report','url':'https://www.bi.go.id/data','trust':'official','included':True,'status':'NEEDS_SELECTION','version':1,'excerpt':'Annual unique customers increased to 120 in the year 2025. Contact person@example.com for details.','columns':{}}];main.save(p,'fixture')
    assert 'excerpt' not in agent_sources(p,sid)[0]
    assert c.post(f'/api/projects/{pid}/messages',json={'text':'Extract this page','request_id':str(uuid.uuid4()),'source_id':sid,'outbound_consent':True}).status_code==409
    r=c.put(f'/api/projects/{pid}/sources/{sid}/privacy-review',json={'version':1,'excerpt':'Annual unique customers increased to 120 in the year 2025.','acknowledge':True});assert r.status_code==200,r.text
    assert agent_sources(r.json(),sid)[0]['excerpt']=='Annual unique customers increased to 120 in the year 2025.'
    assert 'excerpt' not in agent_sources(r.json())[0]

def test_legacy_migration_is_stable_and_preserves_runs(client):
    import backend.main as main
    pid=str(uuid.uuid4());old={'id':pid,'question':'A legacy financing question','context':'','status':'COMPLETED','evidence':{'columns':{'count':{'numeric_count':2,'mean':100}},'filename':'legacy.csv','rows':2},'model':None,'runs':[{'id':'old-run','status':'COMPLETED','result':{'mean':100}}]}
    main.save(old,'legacy_fixture')
    a=client.get(f'/api/projects/{pid}/workspace').json();b=client.get(f'/api/projects/{pid}/workspace').json()
    assert a['sources'][0]['id']==b['sources'][0]['id']
    assert a['runs']==old['runs']
    assert a['evidence'] is None

def test_tavily_contract_and_credential_redaction(client,monkeypatch):
    import backend.main as main
    from backend.connectors import search_web
    captured=[]
    class SearchProvider:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kw):
            captured.append((url,kw['json']))
            return main.httpx.Response(200,json={'results':[{'title':'Industry source','url':'https://www.ojk.go.id/data','content':'Financing statistics'}]})
    monkeypatch.setattr(main.httpx,'AsyncClient',SearchProvider)
    c=client
    r=c.put('/api/connectors/search',json={'provider':'tavily','api_key':'test-tavily-not-real'});assert r.status_code==200
    assert r.json()['search_provider']=='tavily';assert r.json()['search_configured']
    assert 'test-tavily-not-real' not in r.text
    p=project(c)
    r=c.post(f'/api/projects/{p["id"]}/internet-search',json={'query':'OJK financing statistics','access_consent':True});assert r.status_code==200,r.text
    assert captured[0][0]=='https://api.tavily.com/search'
    assert captured[0][1]['search_depth']=='basic'
    assert captured[0][1]['include_answer'] is False
    assert captured[0][1]['include_raw_content'] is False
    assert 'test-tavily-not-real' not in r.text

def test_context_confirmation_and_snapshot_survive_readiness_reload(client):
    c=client;p=project(c);pid=p['id']
    p=c.put(f'/api/projects/{pid}/estimates',json={'note':'Explicit fictional baseline 600000 customers.'}).json()
    r=c.get(f'/api/projects/{pid}/evidence-review').json()
    p=c.post(f'/api/projects/{pid}/evidence-snapshots',json={'revision':p['revision'],'review_hash':r['hash'],'acknowledge':True}).json()
    assert p['sources']==[]
    p=c.get(f'/api/projects/{pid}/workspace').json();assert p['sources']==[]
    assert p['evidence']['hash']==r['hash']

def test_delete_project_removes_encrypted_source_rows(client):
    import backend.main as main
    c=client;p=upload(c,project(c));sid=p['sources'][0]['id'];path=main.DATA/'sources'/(sid+'.enc')
    assert path.exists()
    assert 'person@example.com' not in path.read_bytes().decode()
    assert c.delete(f'/api/projects/{p["id"]}').status_code==200
    assert not path.exists()

def test_html_article_inside_server_form_is_preserved(monkeypatch):
    import asyncio
    from backend import connectors
    article='The policy rate is 5.75 percent for September 2026. This is published macroeconomic evidence, not a customer count.'
    html=f'<html><head><title>Policy report</title></head><body><form id="aspnetForm"><nav>Unrelated navigation</nav><input name="hidden-token" value="secret-value"><article>{article}</article><button>Submit form</button></form></body></html>'.encode()
    class Response:
        status_code=200
        headers={'content-type':'text/html'}
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def aiter_bytes(self):yield html
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def stream(self,*args,**kw):return Response()
    monkeypatch.setattr(connectors.httpx,'AsyncClient',Client)
    result=asyncio.run(connectors.fetch_page('https://www.bi.go.id/policy'))
    assert article in result['excerpt']
    assert 'secret-value' not in result['excerpt']
    assert 'Unrelated navigation' not in result['excerpt']

def test_quoted_numbers_respect_declared_decimal_convention():
    from backend.evidence import quoted_numbers
    assert 5.75 in quoted_numbers('BI-Rate sebesar 5 ,75%, pada Agustus 2026.','decimal_comma')
    assert 575 not in quoted_numbers('BI-Rate sebesar 5 ,75%, pada Agustus 2026.','decimal_comma')
    assert 600000 in quoted_numbers('Jumlah nasabah 600.000 orang.','decimal_comma')
    assert 1234.56 in quoted_numbers('Balance 1,234.56 USD.','decimal_dot')
    with pytest.raises(ValueError):quoted_numbers('5,75%','guess')
