import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.db.models import User
from app.main import app


def _validate_test_database_url(url: str | None) -> str:
    """Validate the dedicated test DB target without exposing URL contents."""
    if not url or not url.strip():
        raise ValueError("TEST_DATABASE_URL is missing; refusing to create a database engine")

    try:
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        raise ValueError("TEST_DATABASE_URL is not a valid SQLAlchemy URL") from None

    failures = []
    if parsed.host not in {"127.0.0.1", "localhost"}:
        failures.append("hostname must be 127.0.0.1 or localhost")
    if parsed.port != 5435:
        failures.append("port must be 5435")
    if parsed.database != "electricity_analytics_test":
        failures.append("database must be electricity_analytics_test")
    if parsed.username != "electricity_test":
        failures.append("username must be electricity_test")
    if parsed.get_backend_name() != "postgresql":
        failures.append("URL must use PostgreSQL")

    if failures:
        raise ValueError(
            "Refusing database access: TEST_DATABASE_URL requirements not met: "
            + "; ".join(failures)
        )
    return url


@pytest.fixture(scope="session")
def test_engine():
    try:
        url = _validate_test_database_url(os.getenv("TEST_DATABASE_URL"))
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture(autouse=True)
def clear_test_data(test_engine):
    with test_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def client(test_engine, monkeypatch):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    from app.api.routes import datasets
    from app.clients.ingestion import NormalizedCSV
    from app.ingestion.pipeline import normalize_csv

    monkeypatch.setattr(
        datasets.ingestion_service_client,
        "normalize",
        lambda content: NormalizedCSV(**normalize_csv(content)),
    )
    uploads = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
    monkeypatch.setattr(datasets, "UPLOAD_DIR", Path(uploads.name))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    uploads.cleanup()


@pytest.fixture
def admin(db_session):
    user = User(username="admin-test", email="admin@test.local", password_hash=hash_password("admin-password-test-123"), role="admin", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def analyst(db_session):
    user = User(username="analyst-test", email="analyst@test.local", password_hash=hash_password("analyst-password-test-123"), role="analyst", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authenticate(client, email: str, password: str):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response
