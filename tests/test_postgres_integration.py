"""Run with NORTH_TEST_POSTGRES_DSN against an explicitly disposable test database."""
import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import connectors

@pytest.mark.skipif(not os.getenv('NORTH_TEST_POSTGRES_DSN'),reason='Disposable PostgreSQL test DSN not configured')
def test_real_postgres_metadata_query_and_privacy():
    import psycopg
    dsn=os.environ['NORTH_TEST_POSTGRES_DSN']
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute('CREATE TABLE IF NOT EXISTS public.north_test_customers(customer_id text, balance numeric, month date)')
        c.execute('TRUNCATE public.north_test_customers')
        c.execute("INSERT INTO public.north_test_customers VALUES ('customer-a',100,'2026-01-01'),('customer-a',120,'2026-02-01'),('customer-b',200,'2026-02-01')")
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='north_readonly'").fetchone():c.execute('CREATE ROLE north_readonly LOGIN')
        c.execute('GRANT USAGE ON SCHEMA public TO north_readonly')
        c.execute('GRANT SELECT ON public.north_test_customers TO north_readonly')
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    config=conninfo_to_dict(dsn);config['user']='north_readonly';readonly=make_conninfo(**config)
    cat=connectors.catalog(readonly,['public'])
    cols={'public.north_test_customers':[x['name'] for x in cat['public.north_test_customers']]}
    assert next(x for x in cat['public.north_test_customers'] if x['name']=='customer_id')['restricted']
    rows,fields,sql=connectors.query_database(readonly,'SELECT COUNT(DISTINCT customer_id) AS active_customers FROM public.north_test_customers',list(cols),cols)
    assert rows==[{'active_customers':'2'}]
    assert 'customer-a' not in str(rows)
    with pytest.raises(ValueError):connectors.query_database(readonly,'SELECT customer_id FROM public.north_test_customers',list(cols),cols)
    # Verify the transaction itself is read-only, independent of the SQL parser.
    with connectors.connection(readonly) as c:
        c.execute('SET TRANSACTION READ ONLY')
        with pytest.raises(psycopg.Error):c.execute('DELETE FROM public.north_test_customers')

@pytest.mark.skipif(not os.getenv('NORTH_TEST_POSTGRES_DSN'),reason='Disposable PostgreSQL test DSN not configured')
def test_real_postgres_workspace_query_scope():
    # This database contains only fixtures created by the previous integration test.
    dsn=os.environ['NORTH_TEST_POSTGRES_DSN'].replace('://postgres@','://north_readonly@')
    with TestClient(app) as c:
        assert c.put('/api/connectors/postgres',json={'dsn':dsn}).status_code==200
        assert dsn not in c.get('/api/connectors').text
        p=c.post('/api/projects',json={'question':'How many unique active customers are in our test portfolio?'}).json();pid=p['id']
        r=c.post(f'/api/projects/{pid}/sources/postgres',json={'label':'Read-only fixture portfolio','schemas':['public'],'access_consent':True});assert r.status_code==200,r.text
        s=r.json()['sources'][-1];sid=s['id']
        r=c.put(f'/api/projects/{pid}/sources/{sid}/tables',json={'version':s['version'],'tables':['public.north_test_customers']});assert r.status_code==200,r.text
        s=r.json()['sources'][-1]
        r=c.post(f'/api/projects/{pid}/sources/{sid}/query',json={'version':s['version'],'query':'SELECT COUNT(DISTINCT customer_id) AS active_customers FROM public.north_test_customers','access_consent':True});assert r.status_code==200,r.text
        s=r.json()['sources'][-1];assert s['columns']['active_customers']['mean']==2
        assert 'customer-a' not in r.text
        assert c.post(f'/api/projects/{pid}/sources/{sid}/query',json={'version':s['version'],'query':'SELECT customer_id FROM public.north_test_customers','access_consent':True}).status_code==422
