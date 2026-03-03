from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
import models, schemas, auth, database
from pydantic import BaseModel
from typing import Optional

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# ── Me response schema ────────────────────────────────────────
class MeOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    candidate_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

@router.get("/me", response_model=MeOut)
def get_me(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    role_obj = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
    role_name = role_obj.role_name if role_obj else "candidate"
    candidate = db.query(models.Candidate).filter(models.Candidate.user_id == current_user.id).first()
    return MeOut(
        id=current_user.id,
        email=current_user.email,
        role=role_name,
        is_active=current_user.is_active,
        candidate_id=candidate.id if candidate else None,
        first_name=candidate.first_name if candidate else None,
        last_name=candidate.last_name if candidate else None,
    )

@router.post("/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    role = db.query(models.Role).filter(models.Role.role_name == user.role_name).first()
    if not role:
        if user.role_name in ["admin", "recruiter", "candidate"]:
            role = models.Role(role_name=user.role_name, description=f"{user.role_name.capitalize()} role")
            db.add(role)
            db.commit()
            db.refresh(role)
        else:
            raise HTTPException(status_code=400, detail="Invalid role specified")

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        password_hash=hashed_password,
        role_id=role.id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    if role.role_name == "candidate":
        candidate_profile = models.Candidate(user_id=new_user.id)
        db.add(candidate_profile)
        db.commit()
        
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = auth.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    role = db.query(models.Role).filter(models.Role.id == user.role_id).first()
    role_name = role.role_name if role else ""

    access_token = auth.create_access_token(
        data={"sub": user.email, "role": role_name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/init")
def initialize_demo_users(db: Session = Depends(database.get_db)):
    """Seed demo users for all roles (idempotent)."""
    created = []
    demo_users = [
        {"email": "admin@jobpull.io", "password": "admin123", "role_name": "admin"},
        {"email": "recruiter@jobpull.io", "password": "recruiter123", "role_name": "recruiter"},
        {"email": "candidate@jobpull.io", "password": "candidate123", "role_name": "candidate"},
    ]
    for du in demo_users:
        if db.query(models.User).filter(models.User.email == du["email"]).first():
            continue
        role = db.query(models.Role).filter(models.Role.role_name == du["role_name"]).first()
        if not role:
            role = models.Role(role_name=du["role_name"], description=f"{du['role_name'].capitalize()} role")
            db.add(role); db.commit(); db.refresh(role)
        new_user = models.User(
            email=du["email"], password_hash=auth.get_password_hash(du["password"]), role_id=role.id
        )
        db.add(new_user); db.commit(); db.refresh(new_user)
        if du["role_name"] == "candidate":
            cand = models.Candidate(
                user_id=new_user.id, first_name="Demo", last_name="Candidate",
                skills=["Python", "SQL", "Data Analysis"], experience_years=3,
                current_title="Data Analyst", location="New York, NY"
            )
            db.add(cand); db.commit()
        created.append(du["email"])
    return {"created": created, "message": "Demo users initialized"}
