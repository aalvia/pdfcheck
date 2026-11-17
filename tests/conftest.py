import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.resolve().as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setenv("AI_MODE", "mock")
    monkeypatch.setenv("EXTERNAL_SYSTEM_MODE", "mock")
    monkeypatch.setenv("MAX_UPLOAD_MB", "10")
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def upload(client: TestClient, path, name: str | None = None):
    return client.post(
        "/api/documents/upload",
        files={"file": (name or path.name, path.read_bytes(), "application/pdf")},
    )
