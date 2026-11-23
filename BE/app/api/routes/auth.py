from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import (
    TOKEN_COOKIE,
    TOKEN_TTL_MINUTES,
    cookie_secure,
    create_access_token,
    verify_password,
)
from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import LoginRequest, UserPublic

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=UserPublic, summary="Authenticate and set an HttpOnly cookie")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    response.set_cookie(
        TOKEN_COOKIE,
        create_access_token(user.id),
        max_age=TOKEN_TTL_MINUTES * 60,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/api",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Clear the authentication cookie")
def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE, path="/api", httponly=True, secure=cookie_secure(), samesite="lax")


@router.get("/me", response_model=UserPublic, summary="Get the authenticated user")
def me(user: User = Depends(get_current_user)):
    return user
