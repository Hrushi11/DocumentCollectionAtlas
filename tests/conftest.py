"""Shared pytest fixtures."""
import pytest

import app.models  # noqa: F401 - register tables on Base.metadata
from app.db import SessionLocal, init_engine


@pytest.fixture
def session():
    """A fresh in-memory database session per test."""
    init_engine("sqlite:///:memory:", create_all=True)
    with SessionLocal() as s:
        yield s
