import os
import tempfile
from pathlib import Path

# Konfiguracja PRZED importem aplikacji: FakeLLM, osobna baza SQLite, dane demo.
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp.as_posix()}",
    "LLM_MODE": "fake",
    "SEED_DEMO_DATA": "true",
    "JWT_SECRET": "test-secret-test-secret-test-secret-123",
    "SMTP_HOST": "",  # testy nie wysyłają e-maili
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, email: str) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": "demo123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def manager(client):
    return _login(client, "marek.zielinski@demo.gov.pl")


@pytest.fixture(scope="session")
def other_manager(client):
    return _login(client, "andrzej.krawczyk@demo.gov.pl")


@pytest.fixture(scope="session")
def employee(client):
    return _login(client, "anna.kowalska@demo.gov.pl")


@pytest.fixture(scope="session")
def hr(client):
    return _login(client, "hr@demo.gov.pl")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@demo.gov.pl")
