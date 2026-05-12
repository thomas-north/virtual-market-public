from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from vmarket.config import get_db_path


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None


def get_engine(db_path: Path | None = None) -> Engine:
    global _engine
    if _engine is None:
        path = db_path or get_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{path}", echo=False)
    return _engine


def init_db(db_path: Path | None = None) -> Engine:
    engine = get_engine(db_path)
    # Import all models so they register on Base.metadata
    import vmarket.models  # noqa: F401
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(db_path: Path | None = None) -> Generator[Session, None, None]:
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session
