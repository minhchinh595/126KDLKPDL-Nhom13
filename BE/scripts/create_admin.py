"""Interactively create the first active administrator account."""

import argparse
import getpass
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.database import get_session_factory  # noqa: E402
from app.db.models import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.email):
        parser.error("--email must be a valid email address")
    password = getpass.getpass("New admin password (minimum 12 characters): ")
    if len(password) < 12:
        parser.error("Password must contain at least 12 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")

    with get_session_factory()() as db:
        admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
        if admins:
            print("An active admin already exists; bootstrap is only allowed for the first admin.", file=sys.stderr)
            return 1
        db.add(User(username=args.username.strip(), email=args.email.strip().lower(), password_hash=hash_password(password), role="admin", is_active=True))
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    print("Admin account created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
