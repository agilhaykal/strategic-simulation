import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend import monitoring as m

class Span:
    def __init__(self,values):self.values=values;self.trace_id=values['trace_context']['trace_id'];self.id='a'*16;self.ended=False
    def update(self,**values):self.values.update(values)
    def end(self):self.ended=True
class Client:
    def __init__(self):self.spans=[]
    def start_observation(self,**values):
        span=Span(values);self.spans.append(span);return span

def test_metrics_exclude_content_and_preserve_nested_worker_context(monkeypatch):
    client=Client();monkeypatch.setattr(m,'client',lambda:client)
    with m.observe('http.request',operation='http',prompt='secret customer',project_ref=m.reference('private project')):
        with ThreadPoolExecutor(max_workers=1) as pool:
            def work():
                with m.observe('assistant.generation',kind='generation',model='openai/gpt-6-luna',query='select secret') as item:
                    item.usage_from({'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30,'cost':0.001},'choices':[{'text':'private reply'}]})
            pool.submit(m.bind_context(work)).result()
    root,child=client.spans
    assert child.values['trace_context']['trace_id']==root.trace_id
    assert child.values['trace_context']['parent_span_id']==root.id
    assert child.values['usage_details']=={'input':20,'output':10,'total':30}
    assert child.values['cost_details']=={'total':0.001}
    assert all(s.ended for s in client.spans)
    serialized=json.dumps([s.values for s in client.spans])
    for secret in ('secret customer','private project','select secret','private reply'):assert secret not in serialized

def test_failure_has_type_without_message(monkeypatch):
    client=Client();monkeypatch.setattr(m,'client',lambda:client)
    with pytest.raises(ValueError):
        with m.observe('assistant.generation'):raise ValueError('password secret')
    values=client.spans[0].values
    assert values['metadata']['exception_type']=='ValueError'
    assert values['level']=='ERROR'
    assert 'password' not in json.dumps(values)

def test_monitoring_failure_does_not_break_product(monkeypatch):
    class Broken:
        def start_observation(self,**kwargs):raise RuntimeError('offline')
    monkeypatch.setattr(m,'client',lambda:Broken())
    with m.observe('simulation.execute') as item:item.set(iterations=1000)

def test_no_cloud_fallback_or_secret_status(monkeypatch):
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY','pk-secret');monkeypatch.setenv('LANGFUSE_SECRET_KEY','sk-secret')
    assert not m.configuration()['enabled']
    monkeypatch.setenv('LANGFUSE_BASE_URL','https://langfuse.staging.ximplify.id')
    assert m.configuration()['enabled']
    assert 'secret' not in json.dumps(m.status())
    monkeypatch.setenv('LANGFUSE_BASE_URL','https://user:pass@example.com')
    assert not m.configuration()['enabled']

def test_real_sdk_exports_only_metrics():
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter=InMemorySpanExporter();provider=TracerProvider();provider.add_span_processor(SimpleSpanProcessor(exporter))
    sdk=Langfuse(public_key='pk-local-unit-test',secret_key='sk-local-unit-test',base_url='http://localhost:1',tracer_provider=provider,span_exporter=exporter)
    span=sdk.start_observation(name='assistant.generation',as_type='generation',model='openai/gpt-6-luna')
    span.update(metadata={'duration_ms':42},usage_details={'input':20,'output':10},cost_details={'total':0.001});span.end()
    provider.force_flush()
    spans=exporter.get_finished_spans()
    assert spans and any('usage' in key for key in spans[0].attributes)
    assert not any(key.endswith('.input') or key.endswith('.output') for key in spans[0].attributes if 'usage' not in key)
    sdk.shutdown()
