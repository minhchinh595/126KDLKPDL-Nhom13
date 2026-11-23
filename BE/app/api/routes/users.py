from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.security import hash_password
from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import UserCreate, UserListResponse, UserPatch, UserPublic, UserStatusPatch

router = APIRouter(prefix="/users", dependencies=[Depends(require_admin)])


def _ensure_last_admin_remains_active(db: Session, target: User, *, is_active: bool, role: str) -> None:
    if target.role == "admin" and target.is_active and (not is_active or role != "admin"):
        active_admins = db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True)).with_for_update()).all()
        if len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="The last active admin cannot be disabled or demoted")


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255), role: str | None = Query(None, pattern="^(admin|analyst)$"),
    is_active: bool | None = None, db: Session = Depends(get_db),
):
    statement = select(User)
    count_statement = select(func.count()).select_from(User)
    filters = []
    if search:
        match = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(match), User.username.ilike(match)))
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))
    if filters:
        statement, count_statement = statement.where(*filters), count_statement.where(*filters)
    total = db.scalar(count_statement) or 0
    items = db.scalars(statement.order_by(User.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": ceil(total / page_size)}


@router.get("/{user_id}", response_model=UserPublic)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("", response_model=UserPublic, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = User(username=payload.username.strip(), email=payload.email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc
    return user


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(user_id: int, payload: UserPatch, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    role = changes.get("role", user.role)
    _ensure_last_admin_remains_active(db, user, is_active=user.is_active, role=role)
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    for key, value in changes.items():
        if value is not None:
            setattr(user, key, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc
    return user


@router.patch("/{user_id}/status", response_model=UserPublic)
def update_user_status(user_id: int, payload: UserStatusPatch, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_last_admin_remains_active(db, user, is_active=payload.is_active, role=user.role)
    user.is_active = payload.is_active
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account status could not be updated") from exc
    return user
