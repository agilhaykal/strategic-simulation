import hashlib, json
import numpy as np
from pathlib import Path

OPS={'add','subtract','multiply','divide','min','max'}
def validate(m):
    if m.get('correlation') or m.get('correlations') or m.get('correlation_matrix'): raise ValueError('Correlated sampling is not supported; do not silently assume independence')
    for key in ('title','horizon','unit'):
        if not isinstance(m.get(key),str) or not m[key].strip(): raise ValueError(f'Missing {key}')
    for key in ('assumptions','limitations'):
        if not isinstance(m.get(key),list) or not all(isinstance(x,str) for x in m[key]): raise ValueError(f'Missing {key}')
    variables=m['variables']
    if not 1 <= len(variables) <= 30: raise ValueError('Use 1–30 variables')
    known=set()
    for v in variables:
        if not isinstance(v.get('evidence_ref'),str) or not v['evidence_ref'].strip(): raise ValueError('Every input needs provenance or an explicit estimate reference')
        if not isinstance(v.get('unit'),str) or not v['unit'].strip(): raise ValueError('Every input needs units')
        if v['id'] in known: raise ValueError('Duplicate variable')
        known.add(v['id'])
        d=v['distribution']; t=d['type']
        if t not in ('fixed','normal','triangular','beta_pert','bernoulli'): raise ValueError('Unsupported distribution')
        for k,x in d.items():
            if k!='type' and (not isinstance(x,(float,int)) or not np.isfinite(x)): raise ValueError('Parameters must be finite numbers')
        if t=='fixed': float(d['value'])
        if t=='normal' and d['std']<=0: raise ValueError('Standard deviation must be positive')
        if t in ('triangular','beta_pert') and not d['min']<=d['mode']<=d['max']: raise ValueError('Invalid bounds')
        if t in ('triangular','beta_pert') and d['min']==d['max']: raise ValueError('Use fixed for equal bounds')
        if t=='bernoulli' and not 0<=d['p']<=1: raise ValueError('Invalid probability')
    def check(e,depth=0):
        if depth>15: raise ValueError('Expression too deep')
        if isinstance(e,(float,int)):
            if not np.isfinite(e): raise ValueError('Nonfinite literal')
        elif isinstance(e,dict) and set(e)=={'ref'}:
            if e['ref'] not in known: raise ValueError('Unknown or forward reference')
        elif isinstance(e,dict) and e.get('op') in OPS and len(e.get('args',[]))==2:
            for a in e['args']: check(a,depth+1)
        else: raise ValueError('Invalid expression; arbitrary code is forbidden')
    if len(m['formula_graph'])>40: raise ValueError('Too many formulas')
    for f in m['formula_graph']:
        if f['output'] in known: raise ValueError('Duplicate output')
        check({'op':f['op'],'args':f['args']}); known.add(f['output'])
    if m['target']['metric'] not in known: raise ValueError('Unknown target KPI')
    if m['target']['operator'] not in ('>=','<='): raise ValueError('Invalid target operator')
    if not np.isfinite(m['target']['value']): raise ValueError('Invalid target')
    ids={v['id'] for v in variables}
    for k,x in m.get('strategy_levers',{}).items():
        if k not in ids or not isinstance(x,(float,int)) or not np.isfinite(x): raise ValueError('Invalid strategy lever')
    return m

def simulate(m,n=10000,seed=42):
    validate(m); rng=np.random.default_rng(seed); draws={}
    for v in m['variables']:
        d=v['distribution']; t=d['type']
        if t=='fixed': a=np.full(n,d['value'],dtype=float)
        elif t=='normal': a=rng.normal(d['mean'],d['std'],n)
        elif t=='triangular': a=rng.triangular(d['min'],d['mode'],d['max'],n)
        elif t=='bernoulli': a=rng.binomial(1,d['p'],n).astype(float)
        else:
            r=(d['mode']-d['min'])/(d['max']-d['min']); a=d['min']+(d['max']-d['min'])*rng.beta(1+4*r,1+4*(1-r),n)
        draws[v['id']]=a
    def calculate(levers):
        values=dict(draws)
        for k,x in levers.items(): values[k]=np.full(n,x,dtype=float)
        def ev(e):
            if isinstance(e,(float,int)): return e
            if 'ref' in e: return values[e['ref']]
            a,b=map(ev,e['args']); op=e['op']
            if op=='divide' and np.any(np.asarray(b)==0): raise ValueError('Division by zero in sampled scenarios')
            return {'add':np.add,'subtract':np.subtract,'multiply':np.multiply,'divide':np.divide,'min':np.minimum,'max':np.maximum}[op](a,b)
        with np.errstate(all='raise'):
            for f in m['formula_graph']: values[f['output']]=ev(f)
        a=np.broadcast_to(values[m['target']['metric']],(n,))
        if not np.all(np.isfinite(a)): raise ValueError('Nonfinite outcomes')
        return a
    base=calculate({}); strategy=calculate(m.get('strategy_levers',{}))
    def stats(a):
        p=float(np.mean(a>=m['target']['value'] if m['target']['operator']=='>=' else a<=m['target']['value']))
        counts,edges=np.histogram(a,bins=24)
        return dict(mean=float(np.mean(a)),p10=float(np.quantile(a,.1)),p50=float(np.median(a)),p90=float(np.quantile(a,.9)),probability=p,probability_standard_error=float(np.sqrt(p*(1-p)/n)),histogram=counts.tolist(),edges=edges.tolist())
    return dict(baseline=stats(base),strategy=stats(strategy),paired_mean_delta=float(np.mean(strategy-base)),iterations=n,seed=seed,rng='PCG64',numpy_version=np.__version__,engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python_lock_sha256=hashlib.sha256(Path(__file__).with_name('requirements.lock').read_bytes()).hexdigest(),dtype='float64',model_hash=hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest(),warnings=['Model validity depends on approved assumptions. Independent input sampling; correlation is not supported in this milestone.'])
