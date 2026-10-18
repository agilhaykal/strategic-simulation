import os, tempfile, time, copy
os.environ['NORTH_DATA_DIR']=tempfile.mkdtemp()
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.engine import simulate,validate

@pytest.fixture(autouse=True)
def isolate_provider_credentials(monkeypatch):
    # Tests must never consume real account credits or depend on injected keys.
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)

MODEL={'title':'Capacity decision','horizon':'12 months','unit':'units/year','assumptions':['Demand from explicit estimate'],'limitations':['No correlation'],'variables':[{'id':'demand','unit':'units/year','evidence_ref':'user estimate','distribution':{'type':'triangular','min':80,'mode':100,'max':120}},{'id':'capacity','unit':'units/year','evidence_ref':'user estimate','distribution':{'type':'fixed','value':90}}],'formula_graph':[{'output':'served','op':'min','args':[{'ref':'demand'},{'ref':'capacity'}]}],'target':{'metric':'served','operator':'>=','value':95},'strategy_levers':{'capacity':110}}
def test_paired_reproducibility():
    a=simulate(MODEL,10000,42);assert a==simulate(MODEL,10000,42)
    assert a['baseline']['probability']==0
    assert .65<a['strategy']['probability']<.8
    assert a['paired_mean_delta']>0
    m=copy.deepcopy(MODEL);m['strategy_levers']={}
    assert simulate(m)['paired_mean_delta']==0

def test_reject_unsafe_models():
    m=copy.deepcopy(MODEL);m['formula_graph'][0]['op']='eval'
    with pytest.raises(ValueError):validate(m)
    m=copy.deepcopy(MODEL);m['formula_graph'][0]['args']=[{'ref':'missing'},1]
    with pytest.raises(ValueError):validate(m)

def test_local_workflow_and_persistence():
    with TestClient(app) as c:
        p=c.post('/api/projects',json={'question':'Should we expand our capacity?','context':'Annual demand target 95 units.'}).json();pid=p['id']
        assert c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'first'}).status_code==409
        assert c.post(f'/api/projects/{pid}/propose').status_code==409
        r=c.post(f'/api/projects/{pid}/evidence',files={'file':('demand.csv','demand\n90\n100\n110\n','text/csv')});assert r.status_code==200
        assert r.json()['evidence']['columns']['demand']['mean']==100
        assert c.post(f'/api/projects/{pid}/approve',json={'model':MODEL,'acknowledge':True}).status_code==200
        r=c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'first'});assert r.status_code==200
        for _ in range(100):
            p=c.get(f'/api/projects/{pid}').json()
            if p['status'] in ('COMPLETED','FAILED'):break
            time.sleep(.02)
        assert p['status']=='COMPLETED'
        assert p['runs'][0]['result']['baseline']['probability']==0
        assert c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'first'}).status_code==200
        assert len(c.get(f'/api/projects/{pid}').json()['runs'])==1
        c.patch(f'/api/projects/{pid}/context',json={'question':'Should we expand capacity next year?','context':'New context'})
        assert c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'second'}).status_code==409
        assert len(c.get(f'/api/projects/{pid}').json()['runs'])==1
        assert c.get(f'/api/projects/{pid}/audit').json()
        assert c.delete(f'/api/projects/{pid}').status_code==200
        assert c.get(f'/api/projects/{pid}').status_code==404

def test_credential_redaction_and_cross_origin():
    with TestClient(app) as c:
        assert c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':'test-not-a-real-key'}).status_code==200
        r=c.get('/api/settings');assert r.json()['key_present'];assert 'test-not-a-real-key' not in r.text
        assert c.post('/api/projects',headers={'Origin':'https://evil.example'},json={'question':'A valid length question'}).status_code==403
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':''})

def test_agent_contract_with_mocked_provider(monkeypatch):
    import backend.main as main
    class Provider:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            assert url=='https://openrouter.ai/api/v1/chat/completions'
            assert kwargs['json']['model']=='openai/gpt-6-luna'
            assert kwargs['json']['messages'][0]['role']=='system'
            return main.httpx.Response(200,json={'choices':[{'message':{'content':main.json.dumps({'questions':[],'explanation':'Capacity model based on explicit estimates.','model':MODEL})}}]})
    monkeypatch.setattr(main.httpx,'AsyncClient',Provider)
    with TestClient(app) as c:
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':'test-not-real'})
        pid=c.post('/api/projects',json={'question':'Should we increase annual capacity?','context':'Use explicit estimates.'}).json()['id']
        r=c.post(f'/api/projects/{pid}/propose')
        assert r.status_code==200
        assert r.json()['status']=='MODEL_PROPOSED'
        assert 'approved_at' not in r.json()
        assert c.post(f'/api/projects/{pid}/runs',json={'idempotency_key':'unsafe'}).status_code==409
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':''})

def test_environment_key_fallback_and_precedence(monkeypatch):
    import backend.main as main
    monkeypatch.setenv('OPENROUTER_API_KEY','environment-test-key')
    with TestClient(app) as c:
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':''})
        r=c.get('/api/settings')
        assert r.json()['key_source']=='environment'
        assert r.json()['key_present'] is True
        assert 'environment-test-key' not in r.text
        assert main.provider_key(main.settings())=='environment-test-key'
        assert 'environment-test-key' not in main.json.dumps(main.settings())
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':'saved-test-key'})
        assert c.get('/api/settings').json()['key_source']=='settings'
        assert main.provider_key(main.settings())=='saved-test-key'
        c.put('/api/settings',json={'model':'openai/gpt-6-luna','api_key':''})
        assert main.provider_key(main.settings())=='environment-test-key'
        monkeypatch.delenv('OPENROUTER_API_KEY')
        assert c.get('/api/settings').json()['key_present'] is False
