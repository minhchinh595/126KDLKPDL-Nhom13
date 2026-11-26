import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.auth import UserCreate  # noqa: E402
from scripts.create_admin import _admin_from_environment, create_first_admin  # noqa: E402


class FakeSession:
    def __init__(self, existing_admin=None):
        self.existing_admin = existing_admin
        self.committed_admin = False
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, _statement):
        return self.existing_admin or (1 if self.committed_admin else None)

    def execute(self, _statement, _parameters):
        return None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1
        if self.added:
            self.committed_admin = True

    def rollback(self):
        self.rollbacks += 1


def valid_environment():
    return {
        "BOOTSTRAP_ADMIN_USERNAME": "team-admin",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
        "BOOTSTRAP_ADMIN_PASSWORD": "a-local-password-123",
    }


def test_bootstrap_creates_first_admin(monkeypatch):
    db = FakeSession()
    monkeypatch.setattr("scripts.create_admin.hash_password", lambda _password: "hashed-value")

    assert create_first_admin(db, _admin_from_environment(valid_environment())) is True
    assert len(db.added) == 1
    assert db.added[0].role == "admin"
    assert db.added[0].is_active is True
    assert db.added[0].password_hash == "hashed-value"
    assert db.commits == 1
    assert db.rollbacks == 0
    assert create_first_admin(db, _admin_from_environment(valid_environment())) is False
    assert len(db.added) == 1
    assert db.commits == 1


def test_bootstrap_refuses_duplicate_admin_without_mutation(monkeypatch):
    db = FakeSession(existing_admin=7)
    monkeypatch.setattr("scripts.create_admin.hash_password", lambda _password: "hashed-value")

    assert create_first_admin(db, _admin_from_environment(valid_environment())) is False
    assert db.added == []
    assert db.commits == 0


def test_missing_environment_variables_are_reported_without_values():
    with pytest.raises(ValueError, match="BOOTSTRAP_ADMIN_USERNAME"):
        _admin_from_environment({})


@pytest.mark.parametrize(
    "field,value",
    [
        ("BOOTSTRAP_ADMIN_PASSWORD", "short"),
        ("BOOTSTRAP_ADMIN_PASSWORD", "p" * 129),
        ("BOOTSTRAP_ADMIN_USERNAME", "x"),
        ("BOOTSTRAP_ADMIN_EMAIL", "not-an-email"),
    ],
)
def test_invalid_bootstrap_input_is_rejected(field, value):
    env = valid_environment()
    env[field] = value

    with pytest.raises(ValueError):
        _admin_from_environment(env)


def test_email_is_normalized_and_password_is_not_in_validation_error():
    env = valid_environment()
    env["BOOTSTRAP_ADMIN_EMAIL"] = "  ADMIN@EXAMPLE.COM "
    assert _admin_from_environment(env).email == "admin@example.com"

    env["BOOTSTRAP_ADMIN_PASSWORD"] = "secret"
    with pytest.raises(ValueError) as exc:
        _admin_from_environment(env)
    assert "secret" not in str(exc.value)
