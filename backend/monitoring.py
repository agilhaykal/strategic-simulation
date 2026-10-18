"""Opt-in, self-hosted Langfuse metrics. Never capture business content or secrets."""
import atexit
import contextvars
import hashlib
import math
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit

_client=None
_signature=None
_lock=threading.Lock()
_parent=contextvars.ContextVar('simplify_observation',default=None)
_counts={'observations_submitted':0,'instrumentation_errors':0}
ALLOWED_FIELDS={'operation','outcome','http_status','attempt','iterations','source_count','result_count','source_kind','validation','duration_ms','project_ref','request_ref','exception_type'}
SAFE_VALUES={'operation':{'http','conversation','clarify','propose_model','decision_brief','internet_search','internet_fetch','database_catalog','database_query','simulation'},'outcome':{'success','error','invalid_response','cancelled'},'source_kind':{'csv','internet','postgres','none'},'validation':{'passed','failed','not_applicable'}}

def reference(value):return hashlib.sha256(str(value).encode()).hexdigest()[:24]
def metadata(values):
    result={}
    for k,v in values.items():
        if k not in ALLOWED_FIELDS:continue
        if k in SAFE_VALUES:
            if v in SAFE_VALUES[k]:result[k]=v
        elif k in ('project_ref','request_ref'):
            if re.fullmatch(r'[a-f0-9]{24}',str(v)):result[k]=v
        elif k=='exception_type':
            if re.fullmatch(r'[A-Za-z]{1,80}',str(v)):result[k]=v
        elif isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v):result[k]=v
    return result

def configuration():
    base=(os.getenv('LANGFUSE_BASE_URL') or os.getenv('LANGFUSE_HOST') or '').strip().rstrip('/')
    public=os.getenv('LANGFUSE_PUBLIC_KEY','').strip();secret=os.getenv('LANGFUSE_SECRET_KEY','').strip()
    disabled=os.getenv('LANGFUSE_ENABLED','true').lower() in ('false','0','off')
    valid=False
    try:
        u=urlsplit(base)
        valid=bool(u.hostname and not u.username and not u.password and not u.query and not u.fragment and (u.scheme=='https' or (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'))))
    except ValueError:pass
    return {'base':base,'public':public,'secret':secret,'configured':bool(base and public and secret and valid),'enabled':bool(not disabled and base and public and secret and valid),'endpoint_valid':valid}

def _new_client(config):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    # A dedicated provider avoids exporting unrelated libraries' automatic spans.
    return Langfuse(public_key=config['public'],secret_key=config['secret'],base_url=config['base'],timeout=5,debug=False,tracing_enabled=True,tracer_provider=TracerProvider(),environment=os.getenv('LANGFUSE_ENVIRONMENT','local'),release=os.getenv('SIMPLIFY_RELEASE','development'),flush_at=10,flush_interval=5,mask=lambda data,**kwargs: metadata(data) if isinstance(data,dict) else '[CONTENT NOT CAPTURED]')

def client():
    global _client,_signature
    c=configuration()
    if not c['enabled']:return None
    signature=hashlib.sha256((c['base']+c['public']+c['secret']).encode()).hexdigest()
    with _lock:
        if _client is not None and signature==_signature:return _client
        try:_client=_new_client(c);_signature=signature
        except Exception:_counts['instrumentation_errors']+=1;return None
    return _client

class Observation:
    def __init__(self,span=None):self.span=span;self.fields={};self.usage=None;self.cost=None
    def set(self,**fields):self.fields.update(metadata(fields))
    def usage_from(self,response):
        usage=response.get('usage',{}) if isinstance(response,dict) else {}
        details={}
        for original,target in (('prompt_tokens','input'),('completion_tokens','output'),('total_tokens','total')):
            n=usage.get(original)
            if isinstance(n,int) and not isinstance(n,bool) and n>=0:details[target]=n
        self.usage=details or None
        cost=usage.get('cost')
        if isinstance(cost,(int,float)) and not isinstance(cost,bool) and math.isfinite(cost) and cost>=0:self.cost={'total':float(cost)}

@contextmanager
def observe(name,*,kind='span',model=None,**fields):
    start=time.perf_counter();span=None;token=None
    c=client()
    # Names are constants in source code, never user-supplied labels or routes.
    if c is not None:
        try:
            parent=_parent.get();trace={'trace_id':parent['trace_id']} if parent else {'trace_id':uuid.uuid4().hex}
            if parent:trace['parent_span_id']=parent['span_id']
            span=c.start_observation(name=name,as_type=kind,trace_context=trace,metadata=metadata(fields),model=model if model and re.fullmatch(r'[A-Za-z0-9._:/-]{1,150}',model) else None)
            token=_parent.set({'trace_id':span.trace_id,'span_id':span.id})
        except Exception:_counts['instrumentation_errors']+=1
    item=Observation(span);item.set(**fields);failed=False
    try:yield item
    except BaseException as exc:
        failed=True;item.set(outcome='error',exception_type=type(exc).__name__)
        raise
    finally:
        item.set(duration_ms=round((time.perf_counter()-start)*1000,2))
        if 'outcome' not in item.fields:item.set(outcome='success')
        if span is not None:
            try:
                span.update(metadata=item.fields,usage_details=item.usage,cost_details=item.cost,level='ERROR' if failed or item.fields.get('outcome') in ('error','invalid_response') else 'DEFAULT',status_message='operation_failed' if failed or item.fields.get('outcome') in ('error','invalid_response') else 'completed')
                span.end();_counts['observations_submitted']+=1
            except Exception:_counts['instrumentation_errors']+=1
        if token is not None:_parent.reset(token)

def bind_context(fn):
    ctx=contextvars.copy_context()
    return lambda *a,**k:ctx.run(fn,*a,**k)

def status():
    c=configuration()
    return {'configured':c['configured'],'enabled':c['enabled'],'endpoint_valid':c['endpoint_valid'],'content_capture':False,**_counts,'delivery_verified':False}

def verify():
    c=client()
    if c is None:return {'authenticated':False,'trace_submitted':False,'delivery_verified':False}
    try:
        authenticated=bool(c.auth_check())
        if not authenticated:return {'authenticated':False,'trace_submitted':False,'delivery_verified':False}
        before=_counts['observations_submitted']
        with observe('monitoring.connection_check',operation='http'):pass
        c.flush()
        return {'authenticated':True,'trace_submitted':_counts['observations_submitted']>before,'delivery_verified':False}
    except Exception:return {'authenticated':False,'trace_submitted':False,'delivery_verified':False}

def shutdown():
    if _client is not None:
        try:_client.shutdown()
        except Exception:pass
atexit.register(shutdown)
