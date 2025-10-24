import os
import sys
import tempfile
from pathlib import Path
import pytest
from typing import Iterator
from fastapi.testclient import TestClient
import time  # Use time module directly for cache TTL

# Ensure src/ is on import path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# Add project root so that `import src.*` works
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Also add src itself so `import main` continues to work
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Ensure test-friendly env before importing app or db
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.gettempdir(), "chem_test.db"))

from src.db import Base, engine  # noqa: E402 - import after setting env
import src.main as main  # noqa: E402  # type: ignore
from src.cache import get_cache as cache_get_cache  # noqa: E402  # type: ignore


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key: str):
        item = self.store.get(key)
        if not item:
            return None
        exp, value = item
        if exp < time.time():
            del self.store[key]
            return None
        return value

    def setex(self, key: str, ttl: int, value: bytes):
        self.store[key] = (time.time() + ttl, value)


@pytest.fixture(autouse=True)
def _setup_db():
    # Drop and recreate tables for a clean state per test
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # Override cache dependency to avoid real Redis in tests
    main.app.dependency_overrides[cache_get_cache] = lambda: FakeCache()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
