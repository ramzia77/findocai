import os
from pathlib import Path

import pytest

# Must be set before any test module imports api.main (which reads settings
# at import time) -- gives every test's TestClient(app) a fresh, isolated,
# in-memory database via its own lifespan()-triggered init_db() call,
# instead of sharing (and polluting) one real findocai.db across the suite.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent.parent / "sample_docs"


@pytest.fixture
def sample_docs_dir() -> Path:
    return SAMPLE_DOCS_DIR


@pytest.fixture(autouse=True)
def _isolated_vectorstore_index_path(tmp_path):
    """Every test gets its own fresh vectorstore index path, reset before
    each test runs. Without this, a test that seeds a fake (e.g. 16-dim)
    vectorstore onto app.state and then hits an endpoint that persists
    (/ingest, DELETE /documents/{id}) would clobber a *shared* path with
    test-fixture data, which a later test's real lifespan() then fails to
    load (dimension mismatch) -- this bit us for real during development."""
    import settings as settings_module

    os.environ["VECTORSTORE_INDEX_PATH"] = str(tmp_path / "test.faiss")
    settings_module.reset_settings_cache()
    yield
