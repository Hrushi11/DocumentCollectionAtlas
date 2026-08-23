"""
SQLAlchemy setup — deliberately free of any Flask import so the domain layer and tests can
use the ORM without a web context (see docs/06 §2). Models (M1) subclass `Base`.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


# Bound to a concrete engine by init_engine().
SessionLocal = sessionmaker(class_=Session, expire_on_commit=False, future=True)

engine = None


def init_engine(database_url: str, create_all: bool = False):
    """Create the engine, bind the session factory, optionally create tables."""
    global engine
    kwargs = {}
    if database_url.endswith(":memory:"):
        # Share one connection so every session sees the same in-memory database.
        kwargs = dict(connect_args={"check_same_thread": False}, poolclass=StaticPool)
    engine = create_engine(database_url, future=True, **kwargs)
    SessionLocal.configure(bind=engine)
    if create_all:
        # Import models so their tables are registered on Base.metadata (no-op until M1).
        try:
            from . import models  # noqa: F401
        except Exception:
            pass
        Base.metadata.create_all(engine)
    return engine
