from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from ..config import Settings

_engine = None


def init_db(settings: Settings) -> None:
    global _engine
    connect_args = (
        {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
    )
    _engine = create_engine(settings.db_url, connect_args=connect_args)
    # import models so create_all sees the tables
    from ..alerts import models  # noqa: F401

    SQLModel.metadata.create_all(_engine)


def get_engine():
    if _engine is None:
        raise RuntimeError("init_db() has not been called")
    return _engine


@contextmanager
def session_scope():
    with Session(get_engine()) as session:
        yield session
        session.commit()
