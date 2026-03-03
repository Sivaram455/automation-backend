from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime
import models, schemas, auth, database
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/admin", tags=["Admin"])

# ─── Schemas ──────────────────────────────────────────────────
class UserCreateAdmin(BaseModel):
    email: EmailStr
    password: str
    role_name: str = "candidate"

class UserUpdateAdmin(BaseModel):
    email: Optional[EmailStr] = None
    role_name: Optional[str] = None

class StatusUpdate(BaseModel):
    is_active: bool

class UserOutAdmin(BaseModel):
    id: int
    email: str
    role_id: int
    role_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    candidate_name: Optional[str] = None

    class Config:
        from_attributes = True

# ─── Users CRUD ───────────────────────────────────────────────
@router.get("/users", response_model=List[UserOutAdmin])
def get_users(
    skip: int = 0, limit: int = 100,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    query = db.query(models.User)
    if role:
        role_obj = db.query(models.Role).filter(models.Role.role_name == role).first()
        if role_obj:
            query = query.filter(models.User.role_id == role_obj.id)
    if search:
        query = query.filter(models.User.email.ilike(f"%{search}%"))
    users = query.offset(skip).limit(limit).all()
    result = []
    for u in users:
        role_obj = db.query(models.Role).filter(models.Role.id == u.role_id).first()
        candidate = db.query(models.Candidate).filter(models.Candidate.user_id == u.id).first()
        name = None
        if candidate and (candidate.first_name or candidate.last_name):
            name = f"{candidate.first_name or ''} {candidate.last_name or ''}".strip()
        result.append(UserOutAdmin(
            id=u.id, email=u.email, role_id=u.role_id,
            role_name=role_obj.role_name if role_obj else None,
            is_active=u.is_active, created_at=u.created_at,
            candidate_name=name
        ))
    return result

@router.post("/users", response_model=UserOutAdmin)
def create_user(
    user: UserCreateAdmin,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(400, "Email already registered")
    role = db.query(models.Role).filter(models.Role.role_name == user.role_name).first()
    if not role:
        if user.role_name in ["admin", "recruiter", "candidate"]:
            role = models.Role(role_name=user.role_name, description=f"{user.role_name.capitalize()} role")
            db.add(role); db.commit(); db.refresh(role)
        else:
            raise HTTPException(400, "Invalid role")
    new_user = models.User(
        email=user.email, password_hash=auth.get_password_hash(user.password), role_id=role.id
    )
    db.add(new_user); db.commit(); db.refresh(new_user)
    if role.role_name == "candidate":
        db.add(models.Candidate(user_id=new_user.id)); db.commit()
    return UserOutAdmin(
        id=new_user.id, email=new_user.email, role_id=new_user.role_id,
        role_name=role.role_name, is_active=new_user.is_active, created_at=new_user.created_at
    )

@router.put("/users/{user_id}", response_model=UserOutAdmin)
def update_user(
    user_id: int, data: UserUpdateAdmin,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if data.email:
        user.email = data.email
    if data.role_name:
        role = db.query(models.Role).filter(models.Role.role_name == data.role_name).first()
        if not role:
            raise HTTPException(400, "Invalid role")
        user.role_id = role.id
    db.commit(); db.refresh(user)
    role_obj = db.query(models.Role).filter(models.Role.id == user.role_id).first()
    return UserOutAdmin(
        id=user.id, email=user.email, role_id=user.role_id,
        role_name=role_obj.role_name if role_obj else None,
        is_active=user.is_active, created_at=user.created_at
    )

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot delete yourself")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user); db.commit()
    return {"message": "User deleted"}

@router.patch("/users/{user_id}/status")
def toggle_user_status(
    user_id: int, data: StatusUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = data.is_active
    db.commit()
    return {"message": f"User {'activated' if data.is_active else 'deactivated'}"}

# ─── Stats ────────────────────────────────────────────────────
@router.get("/stats")
def get_stats(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    total_users = db.query(func.count(models.User.id)).scalar()
    candidate_role = db.query(models.Role).filter(models.Role.role_name == "candidate").first()
    recruiter_role = db.query(models.Role).filter(models.Role.role_name == "recruiter").first()
    total_candidates = db.query(func.count(models.Candidate.id)).scalar() if candidate_role else 0
    total_recruiters = db.query(func.count(models.User.id)).filter(
        models.User.role_id == recruiter_role.id
    ).scalar() if recruiter_role else 0
    total_jobs = db.query(func.count(models.Job.id)).filter(models.Job.is_active == True).scalar()
    total_applications = db.query(func.count(models.JobApplication.id)).scalar()
    assigned = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.status == "assigned"
    ).scalar()
    placed = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.status == "placed"
    ).scalar()
    return {
        "total_users": total_users,
        "total_candidates": total_candidates,
        "total_recruiters": total_recruiters,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "assigned": assigned,
        "placed": placed,
    }

# ─── Reports ──────────────────────────────────────────────────
@router.get("/reports/overview")
def reports_overview(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    return get_stats(db=db, current_user=current_user)

@router.get("/reports/candidates")
def report_candidates(
    skills: Optional[str] = None,
    location: Optional[str] = None,
    experience_min: Optional[int] = None,
    experience_max: Optional[int] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    q = db.query(models.Candidate)
    if location:
        q = q.filter(models.Candidate.location.ilike(f"%{location}%"))
    if experience_min is not None:
        q = q.filter(models.Candidate.experience_years >= experience_min)
    if experience_max is not None:
        q = q.filter(models.Candidate.experience_years <= experience_max)
    candidates = q.offset(skip).limit(limit).all()
    result = []
    for c in candidates:
        user = db.query(models.User).filter(models.User.id == c.user_id).first()
        app_count = db.query(func.count(models.JobApplication.id)).filter(
            models.JobApplication.candidate_id == c.id
        ).scalar()
        candidate_skills = c.skills if c.skills else []
        if skills:
            filter_skills = [s.strip().lower() for s in skills.split(",")]
            if isinstance(candidate_skills, list):
                match = any(
                    any(fs in str(cs).lower() for cs in candidate_skills)
                    for fs in filter_skills
                )
                if not match:
                    continue
        result.append({
            "id": c.id,
            "user_id": c.user_id,
            "email": user.email if user else None,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "phone": c.phone,
            "location": c.location,
            "experience_years": c.experience_years,
            "current_title": c.current_title,
            "skills": candidate_skills,
            "resume_url": c.resume_url,
            "applications_count": app_count,
            "created_at": c.created_at,
        })
    return result

@router.get("/reports/jobs")
def report_jobs(
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    source: Optional[str] = None,
    skills: Optional[str] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    q = db.query(models.Job).filter(models.Job.is_active == True)
    if location:
        q = q.filter(models.Job.location.ilike(f"%{location}%"))
    if job_type:
        q = q.filter(models.Job.job_type.ilike(f"%{job_type}%"))
    if source:
        q = q.filter(models.Job.source.ilike(f"%{source}%"))
    jobs = q.offset(skip).limit(limit).all()
    result = []
    for j in jobs:
        app_count = db.query(func.count(models.JobApplication.id)).filter(
            models.JobApplication.job_id == j.id
        ).scalar()
        job_skills = j.skills if j.skills else []
        if skills:
            filter_skills = [s.strip().lower() for s in skills.split(",")]
            if isinstance(job_skills, list):
                match = any(
                    any(fs in str(js).lower() for js in job_skills)
                    for fs in filter_skills
                )
                if not match:
                    continue
        result.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "job_type": j.job_type,
            "country": j.country,
            "skills": job_skills,
            "salary_min": j.salary_min,
            "salary_max": j.salary_max,
            "source": j.source,
            "applications_count": app_count,
            "created_at": j.created_at,
        })
    return result

@router.get("/reports/applications")
def report_applications(
    status: Optional[str] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    q = db.query(models.JobApplication)
    if status:
        q = q.filter(models.JobApplication.status == status)
    apps = q.order_by(desc(models.JobApplication.applied_at)).offset(skip).limit(limit).all()
    result = []
    for a in apps:
        candidate = db.query(models.Candidate).filter(models.Candidate.id == a.candidate_id).first()
        job = db.query(models.Job).filter(models.Job.id == a.job_id).first()
        user = db.query(models.User).filter(models.User.id == candidate.user_id).first() if candidate else None
        result.append({
            "id": a.id,
            "candidate_id": a.candidate_id,
            "job_id": a.job_id,
            "status": a.status,
            "applied_at": a.applied_at,
            "candidate_name": f"{candidate.first_name or ''} {candidate.last_name or ''}".strip() if candidate else None,
            "candidate_email": user.email if user else None,
            "job_title": job.title if job else None,
            "company": job.company if job else None,
        })
    return result
