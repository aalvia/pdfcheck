"""Conexión SQLite por proceso y una sesión por petición.

FastAPI ejecuta las funciones síncronas en un pool de hilos. Por eso SQLite
lleva check_same_thread en falso y cada petición abre su propia sesión.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    # Los modelos deben registrarse en Base.metadata antes de crear tablas.
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return engine, session_factory
