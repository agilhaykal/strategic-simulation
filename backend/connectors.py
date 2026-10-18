"""Bounded, read-only external connectors. No LLM-generated code execution."""
import ipaddress, socket, re, json
from urllib.parse import urlsplit, unquote
from datetime import date, datetime
import httpx
from bs4 import BeautifulSoup
from .privacy import scrub, sensitive_header, contains_pii

OFFICIAL=('ojk.go.id','bi.go.id','bps.go.id','imf.org','worldbank.org','gaikindo.or.id','aisi.or.id')
def checked_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Use a public HTTPS URL without credentials or a custom port')
    if contains_pii(unquote(url)) or re.search(r'(?i)[?&](?:token|api_key|password|email|phone|customer_id)=',url):raise ValueError('Do not use source URLs containing credentials or personal identifiers')
    host=u.hostname.lower()
    if host=='localhost' or host.endswith(('.local','.internal','.localhost')):raise ValueError('Private destinations are forbidden')
    # Curated primary-source hostnames also work behind a DNS-resolving egress proxy.
    if official(host):return host
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Private or reserved destinations are forbidden')
    return host

def official(host):return any(host==d or host.endswith('.'+d) for d in OFFICIAL)
async def fetch_page(url):
    host=checked_url(url)
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        async with client.stream('GET',url,headers={'User-Agent':'SimplifySimulation-Evidence/0.2','Accept':'text/html,text/plain'}) as r:
            if r.status_code!=200:raise ValueError(f'Source returned HTTP {r.status_code}; redirects require adding the final HTTPS URL explicitly')
            if not any(t in r.headers.get('content-type','') for t in ('text/html','text/plain')):raise ValueError('Only HTML or plain text pages are supported; PDF extraction is not yet supported')
            raw=bytearray()
            async for chunk in r.aiter_bytes():
                raw.extend(chunk)
                if len(raw)>2_000_000:raise ValueError('Page exceeds 2 MB limit')
    soup=BeautifulSoup(bytes(raw),'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else host
    # SharePoint/ASP.NET often wraps the entire article in a server-side form.
    # Remove interactive controls, not their potentially content-bearing ancestor.
    for tag in soup(['script','style','nav','footer','header','input','button','select','textarea','noscript']):tag.decompose()
    text=scrub(soup.get_text(' ',strip=True))[:18000]
    if len(text)<40:raise ValueError('Page has insufficient readable content')
    return {'title':scrub(title)[:200],'excerpt':text,'trust':'official' if official(host) else 'unverified','host':host}

async def search_web(query,key,provider='tavily'):
    if not key:raise ValueError('Configure TAVILY_API_KEY or a Tavily key in Settings, or add an approved source URL directly')
    async with httpx.AsyncClient(timeout=25) as client:
        r=await client.post('https://api.tavily.com/search',json={'api_key':key,'query':scrub(query),'max_results':5,'search_depth':'basic','include_raw_content':False,'include_answer':False})
    if r.status_code!=200:raise ValueError(f'Tavily returned HTTP {r.status_code}')
    return [{'title':scrub(str(i.get('title','')))[:200],'url':i.get('url',''),'description':scrub(str(i.get('content','')))[:600]} for i in r.json().get('results',[]) if str(i.get('url','')).startswith('https://')][:5]

SAFE_FUNCTIONS={'COUNT','SUM','AVG','MIN','MAX','COALESCE','NULLIF','CAST','DATE_TRUNC','EXTRACT','DATE_PART','ROUND','ABS','LOWER','UPPER','LENGTH'}
def validate_sql(sql,allowed_tables,allowed_columns):
    import sqlglot
    from sqlglot import exp
    trees=sqlglot.parse(sql,read='postgres')
    if len(trees)!=1 or not isinstance(trees[0],exp.Select):raise ValueError('Only one SELECT is allowed; CTEs, unions and commands are not supported')
    tree=trees[0]
    if any(tree.find(x) for x in (exp.With,exp.Into,exp.Lock,exp.Subquery,exp.Star)):raise ValueError('No CTEs, writes, locks, subqueries or SELECT *; enumerate approved columns')
    tables=list(tree.find_all(exp.Table))
    if not tables or len(tables)>4:raise ValueError('Query must reference 1–4 approved tables')
    aliases={}
    for t in tables:
        full=f'{t.db}.{t.name}'
        if not t.db or full not in allowed_tables or t.catalog:raise ValueError('Use schema-qualified approved tables only')
        aliases[t.alias_or_name]=full
    for col in tree.find_all(exp.Column):
        name=col.name
        if col.table:
            table=aliases.get(col.table)
            if not table or name not in allowed_columns.get(table,[]):raise ValueError('Column is outside approved scope')
        elif not any(name in allowed_columns.get(table,[]) for table in aliases.values()):raise ValueError('Column is outside approved scope')
    for col in tree.find_all(exp.Column):
        if sensitive_header(col.name):
            parent=col.parent
            if isinstance(parent,exp.Distinct): parent=parent.parent
            if not isinstance(parent,exp.Count):raise ValueError('Identifier columns may only be used inside COUNT / COUNT DISTINCT')
    if tree.find(exp.Dot):raise ValueError('Schema-qualified function calls and custom operators are not supported')
    for cast in tree.find_all(exp.Cast):
        target=cast.args.get('to')
        if target and target.this==exp.DataType.Type.USERDEFINED:raise ValueError('Custom database types are not supported')
    # Alias names are returned to the caller; identifiers cannot become source mappings.
    for node in tree.find_all(exp.Func):
        name=node.name.upper() if isinstance(node,exp.Anonymous) else node.sql_name().upper()
        if name not in SAFE_FUNCTIONS:raise ValueError(f'Function {name} is not in the read-only allowlist')
    return tree.limit(1001).sql(dialect='postgres')

def connection(dsn):
    import psycopg
    return psycopg.connect(dsn,connect_timeout=5,autocommit=False)

def catalog(dsn,schemas):
    if not schemas or len(schemas)>10:raise ValueError('Approve 1–10 schema names')
    with connection(dsn) as c:
        c.execute('SET TRANSACTION READ ONLY')
        c.execute("SET LOCAL statement_timeout = '5000ms'")
        rows=c.execute("SELECT table_schema,table_name,column_name,data_type FROM information_schema.columns WHERE table_schema = ANY(%s) ORDER BY table_schema,table_name,ordinal_position LIMIT 2001",(schemas,)).fetchall()
        if len(rows)>2000:raise ValueError('Schema scope too broad; narrow it')
    result={}
    for schema,table,col,typ in rows:
        result.setdefault(f'{schema}.{table}',[]).append({'name':col,'type':typ,'restricted':sensitive_header(col)})
    return result

def query_database(dsn,sql,allowed_tables,allowed_columns):
    query=validate_sql(sql,allowed_tables,allowed_columns)
    with connection(dsn) as c:
        c.execute('SET TRANSACTION READ ONLY')
        c.execute("SET LOCAL statement_timeout = '5000ms'")
        c.execute("SET LOCAL lock_timeout = '1000ms'")
        c.execute("SET LOCAL search_path = pg_catalog")
        cur=c.execute(query);rows=cur.fetchmany(1001)
        if len(rows)>1000:raise ValueError('Query exceeds 1,000 result rows; aggregate or narrow the period')
        fields=[x.name for x in cur.description]
    if len(set(fields))!=len(fields) or len(fields)>50:raise ValueError('Use unique output aliases; at most 50 columns')
    def value(v):
        if v is None:return None
        if isinstance(v,(date,datetime)):return v.isoformat()
        return str(v)
    return [{k:value(v) for k,v in zip(fields,row)} for row in rows],fields,query
