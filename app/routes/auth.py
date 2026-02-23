from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token, hash_password, require_role, verify_password, get_current_user,
)
from app.database import get_db
from app.models import User
from app.schemas import ChangePasswordRequest, LoginRequest, UserCreate, UserOut, UserUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])

VALID_ROLES = ("admin", "operator", "readonly")


@router.post("/login")
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    token = create_access_token({"sub": user.username, "role": user.role})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 480,
    )
    log_action(db, user, "login", "user", user.id)
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user).model_dump(),
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}


@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.hashed_password = hash_password(data.new_password)
    log_action(db, user, "change_password", "user", user.id, "User changed their own password")
    db.commit()
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


# --- User management (admin only) ---

@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(VALID_ROLES)}")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail=f"Username '{data.username}' already exists")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = User(
        username=data.username,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.flush()

    log_action(db, admin, "create", "user", user.id, f"Created user '{user.username}' with role '{user.role}'")
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes = []
    if data.full_name is not None:
        user.full_name = data.full_name
        changes.append(f"name='{data.full_name}'")
    if data.role is not None:
        if data.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(VALID_ROLES)}")
        user.role = data.role
        changes.append(f"role='{data.role}'")
    if data.active is not None:
        user.active = data.active
        changes.append(f"active={data.active}")
    if data.password is not None:
        if len(data.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        user.hashed_password = hash_password(data.password)
        changes.append("password changed")

    log_action(db, admin, "update", "user", user.id, f"Updated user '{user.username}': {', '.join(changes)}")
    db.commit()
    db.refresh(user)
    return user
