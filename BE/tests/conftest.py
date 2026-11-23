import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.db.models import User
from app.main import app


@pytest.fixture(scope="session")
def test_engine():
    url = os.getenv("TEST_DATABASE_URL", "")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
    parsed = make_url(url)
    if parsed.database != "electricity_analytics_test":
        pytest.fail("Refusing to use any database except electricity_analytics_test")
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
