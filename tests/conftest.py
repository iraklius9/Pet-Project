import os
import sys
import tempfile
from pathlib import Path
import pytest
from typing import Iterator
from fastapi.testclient import TestClient
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///" + os.path.join(tempfile.gettempdir(), "chem_test.db")
)

from src.db import create_all_sync, drop_all_sync  # noqa: E402 # type: ignore
import src.main as main  # noqa: E402  # type: ignore
from src.cache import get_cache as cache_get_cache  # noqa: E402  # type: ignore


class FakeCache:
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        item = self.store.get(key)
        if not item:
            return None
        exp, value = item
        if exp < time.time():
            del self.store[key]
            return None
        return value

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = (time.time() + ttl, value)


@pytest.fixture(autouse=True)
def _setup_db():
    # Drop and recreate tables for a clean state per test
    try:
        drop_all_sync()
    except Exception:
        pass
    create_all_sync()
    yield


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # Override cache dependency to avoid real Redis in tests
    fake = FakeCache()
    main.app.dependency_overrides[cache_get_cache] = lambda: fake
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
