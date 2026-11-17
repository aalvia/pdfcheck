"""Dependencias de FastAPI: configuración y sesión de base de datos."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    db: Session = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
