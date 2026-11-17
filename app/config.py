"""Configuración leída del entorno.

Nada de esto va fijo en las rutas: se cambia de modo mock a Ollama, o de
integración simulada a HTTP, sin modificar el flujo.
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Diosmar Document Automation"
    database_url: str = "sqlite:///./diosmar.db"
    upload_dir: str = "uploads"
    max_upload_mb: int = Field(default=10, ge=1, le=20)

    ai_mode: Literal["mock", "ollama", "auto"] = "auto"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout_seconds: float = 180

    external_system_mode: Literal["mock", "http"] = "mock"
    external_system_url: str = "http://127.0.0.1:8000/api/mock/admin/invoices"
    http_timeout_seconds: float = 10

    @field_validator("ai_mode", "external_system_mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
