import time
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy import Column, String, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from .settings import DATABASE_URL

connect_args: dict[str, Any] = {}
engine_kwargs: dict[str, Any] = {"echo": False, "future": True, "pool_pre_ping": True}
use_static_pool = False

if DATABASE_URL.startswith("sqlite"):
    # Enable cross-thread access
    connect_args["check_same_thread"] = False
    # If using an in-memory DB, enable URI mode and StaticPool so the same
    # in-memory database is shared across all connections.
    if ":memory:" in DATABASE_URL or "file::memory:" in DATABASE_URL:
        connect_args["uri"] = True
        use_static_pool = True

engine_kwargs["connect_args"] = connect_args
if use_static_pool:
    engine_kwargs["poolclass"] = StaticPool

engine: Engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Model(s)

class Molecule(Base):
    __tablename__ = "molecules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    smiles = Column(String(4096), nullable=False)


def _wait_for_db(max_attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """Block until the database is reachable, or raise after attempts."""
    attempts = 0
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return
        except Exception:  # Catch broadly; SQLAlchemy wraps drivers differently
            attempts += 1
            if attempts >= max_attempts:
                raise
            time.sleep(delay_seconds)


def init_db() -> None:
    # Ensure DB is reachable (useful in containerized startup)
    _wait_for_db()
    Base.metadata.create_all(bind=engine)


@contextmanager
def db_session_scope() -> Iterator[Session]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    with db_session_scope() as session:
        yield session
