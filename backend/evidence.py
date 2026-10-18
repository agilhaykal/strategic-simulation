"""Deterministic source profiling, selection, snapshots and compatibility migration."""
import copy, csv, hashlib, io, json, math, re, uuid
from datetime import datetime, timezone
from .privacy import contains_pii, sensitive_header, scrub

def now(): return datetime.now(timezone.utc).isoformat()
def digest(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True, allow_nan=False).encode()).hexdigest()
def upgrade(p):
    if 'messages' not in p:
        p['messages']=[{'id':str(uuid.uuid4()),'role':'user','content':p['question'],'created':p.get('created',now()),'source_id':None}]
        if p.get('context'): p['messages'].append({'id':str(uuid.uuid4()),'role':'user','content':p['context'],'created':now(),'source_id':None})
        old=p.get('proposal')
        if old: p['messages'].append({'id':str(uuid.uuid4()),'role':'assistant','content':old.get('explanation','')+'\n'+'\n'.join(old.get('questions',[])),'created':now(),'source_id':None})
    p.setdefault('sources',[]);p.setdefault('context_confirmed',False);p.setdefault('revision',0)
    p.setdefault('evidence_snapshots',[]);p.setdefault('context_summary',p.get('context') or p['question'])
    p.setdefault('data_requirements',[]);p.setdefault('model_revision',None)
    if p.get('evidence') and 'columns' in p['evidence'] and 'hash' not in p['evidence'] and not p['sources']:
        e=copy.deepcopy(p['evidence']);e.update(id=str(uuid.uuid4()),kind='csv',label=e.get('filename','Legacy CSV'),status='NEEDS_SELECTION',version=1,selection={},pii_columns=[],quality_note='',legacy=True)
        p['sources'].append(e);p['evidence']=None;p.pop('approved_at',None);p['status']='EVIDENCE_REVIEW'
    return p

def active(p):
    if p['status'] in ('QUEUED','RUNNING'): raise ValueError('Wait for the active simulation')

def invalidate(p,context=False):
    active(p);p['revision']+=1;p.pop('approved_at',None);p.pop('approved_snapshot_hash',None)
    p['model_revision']=None;p['model']=None;p.pop('proposal',None);p['evidence']=None;p['status']='CLARIFYING' if context else 'EVIDENCE_REVIEW'
    if context:p['context_confirmed']=False

def parse_csv(raw):
    if len(raw)>2_000_000: raise ValueError('CSV limit is 2 MB')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    fields=reader.fieldnames
    if not fields or len(fields)>50 or len(set(fields))!=len(fields) or any(not x.strip() or len(x)>120 for x in fields): raise ValueError('Use 1–50 unique nonempty headers, at most 120 characters each')
    rows=[]
    for row in reader:
        if None in row: raise ValueError('A CSV row has more values than headers')
        rows.append(row)
        if len(rows)>20000: raise ValueError('CSV limit is 20,000 rows')
    if not rows: raise ValueError('CSV has no data rows')
    return profile(rows,fields)

def profile(rows,fields):
    columns={};preview=[];pii=[];mapping={}
    for i,k in enumerate(fields):
        vals=[r.get(k) for r in rows]
        protected=sensitive_header(k) or any(contains_pii(v) for v in vals if v is not None)
        alias=f'restricted_column_{i+1}' if protected else scrub(k)
        mapping[alias]=k
        if protected:
            pii.append(alias);columns[alias]={'restricted':True,'reason':'Potential personal identifier; excluded from agent context and mapping'};continue
        numbers=[];missing=0;text=0
        for v in vals:
            if v is None or str(v).strip()=='':missing+=1;continue
            try:
                n=float(v)
                if not math.isfinite(n):raise ValueError()
                numbers.append(n)
            except (ValueError,TypeError):text+=1
        item={'restricted':False,'numeric_count':len(numbers),'missing':missing,'text_count':text,'type':'numeric' if len(numbers)==len(rows)-missing and numbers else 'text'}
        if numbers:
            import numpy as np
            item.update(mean=float(np.mean(numbers)),std=float(np.std(numbers)),min=min(numbers),max=max(numbers))
        columns[alias]=item
    # No raw string samples outbound: dates/categories are locally selectable, not auto-disclosed.
    for row in rows[:5]:
        safe={}
        for alias,k in mapping.items():
            if alias in pii:safe[alias]='[REDACTED]'
            elif columns[alias]['type']=='numeric':
                try:safe[alias]=float(row[k]) if row[k] not in ('',None) else None
                except (ValueError,TypeError):safe[alias]=None
            else:safe[alias]='[TEXT HIDDEN]'
        preview.append(safe)
    warnings=[f'{k}: {v["missing"]} missing values' for k,v in columns.items() if not v.get('restricted') and v.get('missing')]
    if pii:warnings.append(f'{len(pii)} potential identifier columns excluded; manual privacy review is still required')
    return {'rows':len(rows),'columns':columns,'preview':preview,'pii_columns':pii,'warnings':warnings}, {'rows':rows,'column_map':mapping}

def select_data(source,raw,spec):
    columns=spec['columns']
    if not columns or any(k not in source['columns'] or source['columns'][k].get('restricted') for k in columns):raise ValueError('Select only available nonrestricted columns')
    if len(set(columns))!=len(columns):raise ValueError('Duplicate selected columns')
    mapping=spec['mapping']
    if not mapping or any(k not in columns for k in mapping):raise ValueError('Map at least one selected numeric column')
    for k,v in mapping.items():
        if source['columns'][k].get('type')!='numeric' and 'numeric_count' not in source['columns'][k]:raise ValueError('Only numeric columns can map to simulation inputs')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,59}',v['variable']):raise ValueError('Use lowercase variable identifiers')
        if not v.get('unit','').strip() or not v.get('definition','').strip():raise ValueError('Every mapped input needs a unit and definition')
        if not v.get('period','').strip() or not v.get('geography','').strip():raise ValueError('Every mapped input needs a period and geography')
    if len({v['variable'] for v in mapping.values()})!=len(mapping):raise ValueError('Duplicate variable mapping')
    rows=raw['rows']; colmap=raw['column_map']
    for f in spec.get('filters',[]):
        k=f['column']
        if k not in columns or source['columns'][k].get('restricted'):raise ValueError('Filter requires a selected nonrestricted column')
        op=f['operator'];value=f['value']
        if op not in ('eq','gte','lte'):raise ValueError('Unsupported filter operator')
        def keep(r):
            x=r.get(colmap[k])
            if op=='eq':return str(x)==str(value)
            try:return float(x)>=float(value) if op=='gte' else float(x)<=float(value)
            except (ValueError,TypeError):return False
        rows=list(filter(keep,rows))
    if not rows:raise ValueError('Filters returned no rows')
    stats={};aggregation=spec.get('aggregation','mean')
    if aggregation not in ('mean','sum','min','max','last'):raise ValueError('Unsupported aggregation')
    for k,meta in mapping.items():
        vals=[]
        for row in rows:
            try:
                n=float(row[colmap[k]])
                if math.isfinite(n):vals.append(n)
            except (ValueError,TypeError,KeyError):pass
        if not vals:raise ValueError(f'{k} has no usable numeric observations')
        import numpy as np
        value={'mean':lambda:float(np.mean(vals)),'sum':lambda:float(np.sum(vals)),'min':lambda:min(vals),'max':lambda:max(vals),'last':lambda:vals[-1]}[aggregation]()
        stats[meta['variable']]={**meta,'column':k,'count':len(vals),'missing_or_invalid':len(rows)-len(vals),'value':value,'mean':float(np.mean(vals)),'std':float(np.std(vals)),'min':min(vals),'max':max(vals),'aggregation':aggregation,'source_id':source['id'],'source_version':source['version']}
    return {'matched_rows':len(rows),'variables':stats,'note':'Last means last row in source order, not necessarily latest date. Aggregation and missingness require review.'}

def review(p):
    issues=[];variables={};sources=[s for s in p['sources'] if s.get('included',True)]
    if not p.get('context_confirmed'):issues.append('Confirm the current decision context')
    for s in sources:
        if s.get('status')!='APPROVED':issues.append(f'{s["label"]}: approve the current source selection')
        if s['kind']=='internet' and s.get('trust')!='official' and not s.get('quality_accepted'):issues.append(f'{s["label"]}: acknowledge source uncertainty')
        for var,v in s.get('selected',{}).get('variables',{}).items():variables.setdefault(var,[]).append(v)
    # No implicit joins, overwrites, or cross-period arithmetic.
    merged={}
    for var,items in variables.items():
        if len(items)>1:
            issues.append(f'{var}: multiple sources map to the same input. Choose one source or rename the mappings; values are never silently merged.')
        else:merged[var]=items[0]
    periods={v.get('period') for items in variables.values() for v in items}
    populations={v.get('geography') for items in variables.values() for v in items}
    if len(sources)>1 and (len(periods)>1 or len(populations)>1) and not p.get('alignment_note','').strip():
        issues.append('Sources span different periods or populations. Document the alignment/lag assumptions before approval.')
    if not sources and not p.get('estimate_note'):issues.append('Add evidence or explicitly document estimates')
    payload={'context_summary':p['context_summary'],'revision':p['revision'],'sources':[copy.deepcopy(s) for s in sources],'variables':merged,'estimate_note':p.get('estimate_note',''),'alignment_note':p.get('alignment_note','')}
    return {'issues':issues,'ready':not issues,'variables':merged,'hash':digest(payload),'payload':payload}

def agent_sources(p,focus_source_id=None):
    result=[]
    for s in p['sources']:
        if not s.get('included',True):continue
        selected=s.get('selection',{}).get('columns',[])
        result.append({k:s[k] for k in ('id','kind','label','status','version','trust','url','period','quality_note','excerpt','selection','selected') if k in s})
        if s['kind']=='internet' and (not s.get('privacy_reviewed') or s['id']!=focus_source_id):
            result[-1].pop('excerpt',None)
            result[-1]['privacy_status']='Text withheld until user privacy review'
        result[-1]['columns']={k:(v if selected else {field:v[field] for field in ('type','missing','numeric_count','text_count') if field in v}) for k,v in s.get('columns',{}).items() if not v.get('restricted') and (not selected or k in selected)}
    return result


def quoted_numbers(quote,number_format):
    """Parse only numeric tokens present in the quote using an explicit source locale."""
    if number_format not in ('decimal_comma','decimal_dot'):raise ValueError('Specify the source number format')
    compact=re.sub(r'(?<=\d)\s+(?=[.,])|(?<=[.,])\s+(?=\d)','',quote)
    tokens=re.findall(r'(?<![\w.,])[+-]?\d+(?:[.,]\d+)*(?![\w.,])',compact)
    values=[]
    for token in tokens:
        normalized=token.replace('.','').replace(',','.') if number_format=='decimal_comma' else token.replace(',','')
        try:
            value=float(normalized)
            if math.isfinite(value):values.append(value)
        except ValueError:continue
    return values
