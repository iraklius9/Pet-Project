import time
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import Column, String, create_engine, text
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from .settings import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Molecule(Base):
    __tablename__ = "molecules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    smiles = Column(String(4096), nullable=False)


def _wait_for_db(max_attempts: int = 30, delay_seconds: float = 1.0):
    for _ in range(max_attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return
        except Exception:
            time.sleep(delay_seconds)
    raise RuntimeError("Database is not reachable after waiting")


def init_db():
    _wait_for_db()
    Base.metadata.create_all(bind=engine)


@contextmanager
def db_session_scope():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    with db_session_scope() as session:
        yield session
