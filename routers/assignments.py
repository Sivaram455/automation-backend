from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import models, auth, database
import os
from services.job_scraper import compute_match_score, extract_resume_text, extract_skills_from_text
from pydantic import BaseModel

router = APIRouter(tags=["Assignments"])


# ─── Schemas ──────────────────────────────────────────────────
class AssignmentOut(BaseModel):
    application_id: int
    candidate_id: int
    job_id: int
    status: str
    candidate_name: Optional[str]
    candidate_email: Optional[str]
    job_title: Optional[str]
    company: Optional[str]
    match_score: Optional[int] = None

    class Config:
        from_attributes = True

def get_candidate_resume_skills(candidate: models.Candidate) -> list:
    if not candidate or not candidate.resume_url:
        return []
    if candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        return extract_skills_from_text(text)
    return []


# ─── Manual assign ────────────────────────────────────────────
@router.post("/jobs/{job_id}/assign/{candidate_id}")
def assign_job_to_candidate(
    job_id: int, candidate_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.is_active == True).first()
    if not job:
        raise HTTPException(404, "Job not found or inactive")

    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    existing = db.query(models.JobApplication).filter(
        models.JobApplication.candidate_id == candidate_id,
        models.JobApplication.job_id == job_id
    ).first()

    if existing:
        # Update to assigned status
        existing.status = "assigned"
        db.commit()
        return {"message": "Job assignment updated", "application_id": existing.id}

    app = models.JobApplication(candidate_id=candidate_id, job_id=job_id, status="assigned")
    db.add(app); db.commit(); db.refresh(app)
    return {"message": "Job assigned successfully", "application_id": app.id}


# ─── Auto-assign: best jobs for a candidate based on skills ───
@router.post("/candidates/{candidate_id}/auto-assign")
def auto_assign_jobs(
    candidate_id: int,
    top_n: int = 5,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    jobs = db.query(models.Job).filter(models.Job.is_active == True).all()
    resume_skills = get_candidate_resume_skills(candidate)
    # Score all jobs
    scored = [(j, compute_match_score(candidate, j, extra_skills=resume_skills)) for j in jobs]
    scored.sort(key=lambda x: x[1], reverse=True)

    assigned = []
    for job, score in scored[:top_n]:
        if score < 30:
            continue  # skip low matches
        existing = db.query(models.JobApplication).filter(
            models.JobApplication.candidate_id == candidate_id,
            models.JobApplication.job_id == job.id
        ).first()
        if existing:
            existing.status = "assigned"
            db.commit()
            assigned.append({"job_id": job.id, "title": job.title, "score": score, "status": "updated"})
        else:
            app = models.JobApplication(candidate_id=candidate_id, job_id=job.id, status="assigned")
            db.add(app); db.commit()
            assigned.append({"job_id": job.id, "title": job.title, "score": score, "status": "new"})

    return {"candidate_id": candidate_id, "assigned_jobs": assigned}


# ─── Get job matches for a candidate ──────────────────────────
@router.get("/candidates/{candidate_id}/job-matches")
def get_job_matches(
    candidate_id: int,
    min_score: int = 0,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter", "candidate"]))
):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    # Candidates can only see their own matches
    role = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
    if role and role.role_name == "candidate" and candidate.user_id != current_user.id:
        raise HTTPException(403, "Forbidden")

    jobs = db.query(models.Job).filter(models.Job.is_active == True).all()
    resume_skills = get_candidate_resume_skills(candidate)
    scored = [
        {
            "job_id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "job_type": j.job_type,
            "skills": j.skills,
            "salary_min": j.salary_min,
            "salary_max": j.salary_max,
            "apply_url": j.apply_url,
            "match_score": compute_match_score(candidate, j, extra_skills=resume_skills),
        }
        for j in jobs
    ]
    scored = [s for s in scored if s["match_score"] >= min_score]
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return {"candidate_id": candidate_id, "matches": scored[:50]}


# ─── List all assignments ─────────────────────────────────────
@router.get("/", response_model=List[AssignmentOut])
def get_assignments(
    status: Optional[str] = None,
    candidate_id: Optional[int] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    q = db.query(models.JobApplication)
    if status:
        q = q.filter(models.JobApplication.status == status)
    if candidate_id:
        q = q.filter(models.JobApplication.candidate_id == candidate_id)
    apps = q.offset(skip).limit(limit).all()

    result = []
    for a in apps:
        candidate = db.query(models.Candidate).filter(models.Candidate.id == a.candidate_id).first()
        job = db.query(models.Job).filter(models.Job.id == a.job_id).first()
        user = db.query(models.User).filter(models.User.id == candidate.user_id).first() if candidate else None
        resume_skills = get_candidate_resume_skills(candidate) if candidate else []
        score = compute_match_score(candidate, job, extra_skills=resume_skills) if (candidate and job) else None
        result.append(AssignmentOut(
            application_id=a.id,
            candidate_id=a.candidate_id,
            job_id=a.job_id,
            status=a.status,
            candidate_name=f"{candidate.first_name or ''} {candidate.last_name or ''}".strip() if candidate else None,
            candidate_email=user.email if user else None,
            job_title=job.title if job else None,
            company=job.company if job else None,
            match_score=score,
        ))
    return result


# ─── Update assignment status ─────────────────────────────────
@router.patch("/{application_id}/status")
def update_assignment_status(
    application_id: int,
    new_status: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    valid = ["applied", "assigned", "interviewing", "placed", "rejected"]
    if new_status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid}")
    app = db.query(models.JobApplication).filter(models.JobApplication.id == application_id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    app.status = new_status
    db.commit()
    return {"message": f"Status updated to '{new_status}'"}
