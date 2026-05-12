from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from vmarket.config import get_db_path
from vmarket.migrations import run_migrations


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_engine_path: Path | None = None


def get_engine(db_path: Path | None = None) -> Engine:
    global _engine, _engine_path
    path = (db_path or get_db_path()).expanduser()
    if _engine is None or _engine_path != path:
        if _engine is not None:
            _engine.dispose()
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{path}", echo=False)
        _engine_path = path
    return _engine


def init_db(db_path: Path | None = None) -> Engine:
    engine = get_engine(db_path)
    # Import all models so they register on Base.metadata
    import vmarket.models  # noqa: F401
    Base.metadata.create_all(engine)
    run_migrations(engine)
    return engine


@contextmanager
def get_session(db_path: Path | None = None) -> Generator[Session, None, None]:
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session
