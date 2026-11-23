from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.core.security import TOKEN_COOKIE, decode_access_token

cookie_auth = APIKeyCookie(name=TOKEN_COOKIE, scheme_name="JWT HttpOnly cookie", auto_error=False)


def get_current_user(token: str | None = Security(cookie_auth), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return dependency


require_admin = require_roles("admin")
require_analyst = require_roles("admin", "analyst")
