import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from vmarket.db import Base, _engine as _global_engine
import vmarket.db as db_module
import vmarket.models  # noqa: F401 — registers all models


@pytest.fixture
def session():
    """In-memory SQLite session, rolled back after each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    # Patch the global engine so services/repos use the test engine
    original = db_module._engine
    db_module._engine = engine
    with Session(engine) as s:
        yield s
        s.rollback()
    db_module._engine = original
    engine.dispose()
