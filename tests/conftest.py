import os
import tempfile
os.environ['NORTH_DATA_DIR']=tempfile.mkdtemp(prefix='north-tests-')
import pytest

@pytest.fixture(autouse=True)
def isolate_external_bindings(monkeypatch):
    for name in ('OPENROUTER_API_KEY','BRAVE_SEARCH_API_KEY','TAVILY_API_KEY','NORTH_POSTGRES_DSN','LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY','LANGFUSE_BASE_URL','LANGFUSE_HOST'):
        monkeypatch.delenv(name,raising=False)
    from backend.main import db
    with db() as c:c.execute('DELETE FROM settings')
