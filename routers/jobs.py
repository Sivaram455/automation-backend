from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth, database
import os
from services.job_scraper import pull_jobs_from_usa_portals, extract_resume_text, extract_skills_from_text, normalize_candidate_skills

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"]
)

@router.get("/my-applications")
def get_my_applications(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    candidate = db.query(models.Candidate).filter(models.Candidate.user_id == current_user.id).first()
    if not candidate:
        return []
    apps = db.query(models.JobApplication).filter(
        models.JobApplication.candidate_id == candidate.id
    ).all()
    result = []
    for a in apps:
        job = db.query(models.Job).filter(models.Job.id == a.job_id).first()
        result.append({
            "application_id": a.id,
            "job_id": a.job_id,
            "status": a.status,
            "applied_at": a.applied_at,
            "job_title": job.title if job else None,
            "company": job.company if job else None,
            "location": job.location if job else None,
            "job_type": job.job_type if job else None,
            "salary_min": job.salary_min if job else None,
            "salary_max": job.salary_max if job else None,
            "apply_url": job.apply_url if job else None,
            "skills": job.skills if job else [],
        })
    return result

@router.get("/", response_model=List[schemas.JobOut])
def get_jobs(
    skip: int = 0, limit: int = 50,
    location: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    skills: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(database.get_db)
):
    q = db.query(models.Job).filter(models.Job.is_active == True)
    if location:
        q = q.filter(models.Job.location.ilike(f"%{location}%"))
    if job_type:
        q = q.filter(models.Job.job_type.ilike(f"%{job_type}%"))
    if search:
        q = q.filter(
            models.Job.title.ilike(f"%{search}%") |
            models.Job.company.ilike(f"%{search}%") |
            models.Job.description.ilike(f"%{search}%")
        )
    jobs = q.offset(skip).limit(limit).all()
    # Filter by skills in Python (JSON field)
    if skills:
        filter_skills = [s.strip().lower() for s in skills.split(",")]
        def has_skill(job):
            if not job.skills:
                return False
            job_skills = [str(s).lower() for s in (job.skills if isinstance(job.skills, list) else [])]
            return any(fs in js or js in fs for fs in filter_skills for js in job_skills)
        jobs = [j for j in jobs if has_skill(j)]
    return jobs

@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(database.get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@router.post("/", response_model=schemas.JobOut)
def create_job(job: schemas.JobCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))):
    new_job = models.Job(**job.model_dump())
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

@router.put("/{job_id}", response_model=schemas.JobOut)
def update_job(job_id: int, job: schemas.JobCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(404, "Job not found")
    for k, v in job.model_dump(exclude_unset=True).items():
        setattr(db_job, k, v)
    db.commit(); db.refresh(db_job)
    return db_job

@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.require_role(["admin"]))):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(404, "Job not found")
    db_job.is_active = False
    db.commit()
    return {"message": "Job deactivated"}

@router.post("/pull")
def trigger_job_pull(
    query: str = "",
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    """Pull live jobs from Remotive, The Muse, Working Nomads. Optionally filter by keyword."""
    new_jobs_count = pull_jobs_from_usa_portals(db, query=query)
    total_jobs = db.query(models.Job).filter(models.Job.is_active == True).count()
    return {
        "message": f"Pulled {new_jobs_count} new jobs",
        "new_jobs": new_jobs_count,
        "total_jobs": total_jobs
    }


@router.post("/pull-for-candidates")
def trigger_job_pull_for_all_candidates(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin"]))
):
    """
    Pull jobs from all portals using skill keywords extracted from all candidate profiles.
    This ensures job suggestions are relevant to the actual talent pool.
    """
    candidates = db.query(models.Candidate).all()
    keyword_list = []
    for c in candidates:
        skills = normalize_candidate_skills(c)
        resume_skills = []
        if c.resume_url and c.resume_url.startswith("/static/"):
            local_path = os.path.join("uploads", c.resume_url.replace("/static/", ""))
            text = extract_resume_text(local_path)
            resume_skills = extract_skills_from_text(text)
        combined = skills + resume_skills
        if c.current_title:
            combined += [w.lower() for w in c.current_title.split() if len(w) > 3]
        for s in combined:
            if s and s not in keyword_list:
                keyword_list.append(s)

    total_new = 0
    # Pull per category keyword (deduplicated)
    pulled_queries = set()
    for kw in keyword_list[:10]:  # limit to 10 to avoid rate limits
        if kw not in pulled_queries:
            total_new += pull_jobs_from_usa_portals(db, query=kw)
            pulled_queries.add(kw)
    if total_new == 0:
        total_new += pull_jobs_from_usa_portals(db)

    total_jobs = db.query(models.Job).filter(models.Job.is_active == True).count()
    return {
        "message": f"Pulled {total_new} new jobs based on candidates' skills and resumes",
        "new_jobs": total_new,
        "total_jobs": total_jobs,
        "keywords_used": list(pulled_queries)
    }


@router.post("/pull-for-me")
def pull_jobs_for_me(
    max_keywords: int = 10,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    candidate = db.query(models.Candidate).filter(models.Candidate.user_id == current_user.id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    skills = normalize_candidate_skills(candidate)
    resume_skills = []
    if candidate.resume_url and candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        resume_skills = extract_skills_from_text(text)
    combined = skills + resume_skills
    if candidate.current_title:
        combined += [w.lower() for w in candidate.current_title.split() if len(w) > 3]
    keywords = []
    for s in combined:
        if s and s not in keywords:
            keywords.append(s)
    total_new = 0
    for kw in keywords[:max_keywords]:
        total_new += pull_jobs_from_usa_portals(db, query=kw)
    if total_new == 0:
        total_new += pull_jobs_from_usa_portals(db)
    total_jobs = db.query(models.Job).filter(models.Job.is_active == True).count()
    return {
        "message": f"Pulled {total_new} new jobs for your profile",
        "new_jobs": total_new,
        "total_jobs": total_jobs,
        "keywords_used": keywords[:max_keywords]
    }


@router.post("/pull-for-candidate/{candidate_id}")
def pull_jobs_for_candidate(
    candidate_id: int,
    max_keywords: int = 10,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    skills = normalize_candidate_skills(candidate)
    resume_skills = []
    if candidate.resume_url and candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        resume_skills = extract_skills_from_text(text)
    combined = skills + resume_skills
    if candidate.current_title:
        combined += [w.lower() for w in candidate.current_title.split() if len(w) > 3]
    keywords = []
    for s in combined:
        if s and s not in keywords:
            keywords.append(s)
    total_new = 0
    for kw in keywords[:max_keywords]:
        total_new += pull_jobs_from_usa_portals(db, query=kw)
    if total_new == 0:
        total_new += pull_jobs_from_usa_portals(db)
    total_jobs = db.query(models.Job).filter(models.Job.is_active == True).count()
    return {
        "message": f"Pulled {total_new} new jobs for candidate {candidate_id}",
        "new_jobs": total_new,
        "total_jobs": total_jobs,
        "keywords_used": keywords[:max_keywords]
    }

@router.post("/{job_id}/apply", response_model=schemas.JobApplicationOut)
def apply_to_job(job_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.require_role(["candidate"]))):
    candidate = db.query(models.Candidate).filter(models.Candidate.user_id == current_user.id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
        
    job = db.query(models.Job).filter(models.Job.id == job_id, models.Job.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or inactive")
        
    existing_app = db.query(models.JobApplication).filter(
        models.JobApplication.candidate_id == candidate.id,
        models.JobApplication.job_id == job_id
    ).first()
    
    if existing_app:
        raise HTTPException(status_code=400, detail="Already applied to this job")
        
    application = models.JobApplication(candidate_id=candidate.id, job_id=job.id, status="applied")
    db.add(application)
    db.commit()
    db.refresh(application)
    return application
