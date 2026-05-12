import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import vmarket.db as db_module
import vmarket.models  # noqa: F401 — registers all models
from vmarket.config import get_db_path
from vmarket.db import Base


@pytest.fixture
def session():
    """In-memory SQLite session, rolled back after each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    # Patch the global engine so services/repos use the test engine
    original = db_module._engine
    original_path = db_module._engine_path
    db_module._engine = engine
    db_module._engine_path = get_db_path().expanduser()
    with Session(engine) as s:
        yield s
        s.rollback()
    db_module._engine = original
    db_module._engine_path = original_path
    engine.dispose()
