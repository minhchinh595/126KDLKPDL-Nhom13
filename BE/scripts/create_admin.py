"""Create the first administrator from local environment configuration."""

import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.schemas.auth import UserCreate  # noqa: E402


REQUIRED_ENV = (
    "BOOTSTRAP_ADMIN_USERNAME",
    "BOOTSTRAP_ADMIN_EMAIL",
    "BOOTSTRAP_ADMIN_PASSWORD",
)


def _admin_from_environment(environ: dict[str, str]) -> UserCreate:
    missing = [name for name in REQUIRED_ENV if not environ.get(name)]
    if missing:
        raise ValueError("Missing required environment variable(s): " + ", ".join(missing))

    username = environ["BOOTSTRAP_ADMIN_USERNAME"].strip()
    email = environ["BOOTSTRAP_ADMIN_EMAIL"].strip().lower()
    password = environ["BOOTSTRAP_ADMIN_PASSWORD"]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("BOOTSTRAP_ADMIN_EMAIL must be a valid email address")
    try:
        return UserCreate(username=username, email=email, password=password, role="admin")
    except Exception as exc:
        fields = ", ".join(
            ".".join(str(part) for part in error.get("loc", ()))
            for error in getattr(exc, "errors", lambda: [])()
        )
        raise ValueError("Bootstrap Admin input is invalid" + (f" ({fields})" if fields else "")) from None


def create_first_admin(db, credentials: UserCreate) -> bool:
    """Insert the first Admin only; return False if any Admin already exists."""
    # Serialize concurrent bootstrap attempts on PostgreSQL while this transaction checks and inserts.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 731942018})
    existing_admin = db.scalar(select(User.id).where(User.role == "admin").limit(1))
    if existing_admin is not None:
        return False

    db.add(
        User(
            username=credentials.username,
            email=credentials.email,
            password_hash=hash_password(credentials.password),
            role="admin",
            is_active=True,
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def main() -> int:
    try:
        credentials = _admin_from_environment(os.environ)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Importing the DB module loads local .env configuration; defer it until actual CLI execution.
    from app.db.database import get_session_factory

    with get_session_factory()() as db:
        try:
            created = create_first_admin(db, credentials)
        except Exception:
            # Avoid printing SQLAlchemy errors that may contain connection details.
            print("Could not create the bootstrap Admin; inspect local logs securely.", file=sys.stderr)
            return 1

    if not created:
        print("An Admin already exists; bootstrap refused to create a duplicate.", file=sys.stderr)
        return 1
    print("Bootstrap Admin created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
