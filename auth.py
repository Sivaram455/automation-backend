from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import os

import bcrypt

# ──────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key_here_please_change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        hp = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
        pp = plain_password.encode('utf-8') if isinstance(plain_password, str) else plain_password
        return bcrypt.checkpw(pp, hp)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    pw = password.encode('utf-8') if isinstance(password, str) else password
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user


def require_role(allowed_roles: list):
    def role_dependency(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        user_role = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
        if user_role and user_role.role_name == "admin":
            return current_user
            
        if not user_role or user_role.role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {allowed_roles}"
            )
        return current_user
    return role_dependency
