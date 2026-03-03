from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth, database
from services.job_scraper import get_matched_jobs_for_candidate, pull_jobs_from_usa_portals, extract_resume_text, extract_skills_from_text, normalize_candidate_skills
import os
import uuid

router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"]
)


@router.get("/me", response_model=schemas.CandidateOut)
def get_my_profile(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return candidate


@router.put("/me", response_model=schemas.CandidateOut)
def update_my_profile(
    profile_data: schemas.CandidateCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    """Update candidate profile including skills, title, experience."""
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        # Create one if missing
        candidate = models.Candidate(user_id=current_user.id)
        db.add(candidate)

    for key, value in profile_data.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)

    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/me/matched-jobs")
def get_my_matched_jobs(
    min_score: int = 20,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    """
    Return jobs matched to the logged-in candidate's skills and profile.
    Candidate must have skills set in their profile.
    """
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        return {"candidate_id": None, "matches": [], "message": "Complete your profile to get job matches"}

    extra_skills = []
    if candidate.resume_url and candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        extra_skills = extract_skills_from_text(text)

    matches = get_matched_jobs_for_candidate(db, candidate, min_score=min_score, top_n=50, extra_skills=extra_skills)

    # Enrich with application status
    for match in matches:
        app = db.query(models.JobApplication).filter(
            models.JobApplication.candidate_id == candidate.id,
            models.JobApplication.job_id == match["job_id"]
        ).first()
        match["application_status"] = app.status if app else None

    return {
        "candidate_id": candidate.id,
        "profile_complete": bool((candidate.skills or extra_skills) and candidate.current_title),
        "matches": matches
    }


@router.post("/me/resume")
def upload_my_resume(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".pdf", ".doc", ".docx", ".txt"]:
        raise HTTPException(status_code=400, detail="Invalid file type")

    target_dir = os.path.join("uploads", "resumes")
    os.makedirs(target_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(target_dir, unique_name)

    with open(path, "wb") as f:
        f.write(file.file.read())

    url = f"/static/resumes/{unique_name}"
    candidate.resume_url = url
    db.commit()
    db.refresh(candidate)

    return {"resume_url": url}


@router.post("/me/auto-pull-match-assign")
def auto_pull_match_assign(
    top_n: int = 5,
    min_score: int = 30,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    skills = normalize_candidate_skills(candidate)
    extra_skills = []
    if candidate.resume_url:
        if candidate.resume_url.startswith("/static/"):
            local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
            text = extract_resume_text(local_path)
            extra_skills = extract_skills_from_text(text)

    keywords = list(dict.fromkeys([s for s in skills + extra_skills if s]))[:10]
    new_jobs = 0
    for kw in keywords[:5]:
        new_jobs += pull_jobs_from_usa_portals(db, query=kw)
    if new_jobs == 0:
        new_jobs += pull_jobs_from_usa_portals(db)

    matches = get_matched_jobs_for_candidate(db, candidate, min_score=min_score, top_n=50, extra_skills=extra_skills)
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    select = matches[:top_n]

    assigned = []
    for m in select:
        existing = db.query(models.JobApplication).filter(
            models.JobApplication.candidate_id == candidate.id,
            models.JobApplication.job_id == m["job_id"]
        ).first()
        if existing:
            existing.status = "assigned"
            db.commit()
            application_id = existing.id
        else:
            app = models.JobApplication(candidate_id=candidate.id, job_id=m["job_id"], status="assigned")
            db.add(app); db.commit(); db.refresh(app)
            application_id = app.id

        gen_dir = os.path.join("uploads", "resumes_generated")
        os.makedirs(gen_dir, exist_ok=True)
        out_path = os.path.join(gen_dir, f"{candidate.id}_{m['job_id']}.txt")
        full_name = f"{candidate.first_name or ''} {candidate.last_name or ''}".strip() or "Candidate"
        phone = candidate.phone or ""
        location = candidate.location or ""
        title = candidate.current_title or "Professional"
        exp = candidate.experience_years if candidate.experience_years is not None else ""
        skill_text = ", ".join(candidate.skills if isinstance(candidate.skills, list) else [])
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"{full_name}\n")
            f.write(f"{location} | {phone}\n")
            f.write(f"Title: {title} | Experience: {exp} years\n\n")
            f.write("Summary\n")
            f.write(f"{title} with experience delivering results. Skilled in {skill_text}.\n\n")
            f.write("Skills\n")
            f.write(f"{skill_text}\n\n")
            f.write("Work Experience\n")
            f.write(f"{title} – {m['company'] or 'Company'}\n")
            f.write("• Contributed to projects leveraging listed skills\n")
            f.write("• Collaborated across teams to deliver outcomes\n\n")
            f.write("Education\n")
            f.write("• Education details\n")
        resume_generated_url = f"/static/resumes_generated/{os.path.basename(out_path)}"

        user = db.query(models.User).filter(models.User.id == candidate.user_id).first()
        email = user.email if user else ""
        template_path = os.path.join("templates", "resume_template.html")
        if os.path.exists(template_path):
            try:
                with open(template_path, "r", encoding="utf-8") as tf:
                    tpl = tf.read()
                summary = f"{title} with experience delivering results. Skilled in {skill_text}. Targeting roles like {m['title']}."
                skills_grid = "\n".join([f"<div>{s}</div>" for s in (candidate.skills if isinstance(candidate.skills, list) else [])])
                exp_items = "\n".join([
                    "<li>Analyzed business and data workflows using SQL and Python.</li>",
                    "<li>Gathered requirements and documented functional specifications.</li>",
                    "<li>Built dashboards and reports using BI tools.</li>",
                    "<li>Collaborated across teams to deliver outcomes.</li>",
                ])
                education = "M.S. or Bachelor’s degree – Details"
                html = tpl
                html = html.replace("{{FULL_NAME}}", full_name or "")
                html = html.replace("{{EMAIL}}", email or "")
                html = html.replace("{{PHONE}}", phone or "")
                html = html.replace("{{LOCATION}}", location or "")
                html = html.replace("{{SUMMARY}}", summary)
                html = html.replace("{{SKILLS_GRID}}", skills_grid or "<div>Skills</div>")
                html = html.replace("{{JOB_TITLE}}", m["title"] or title)
                html = html.replace("{{JOB_DATE}}", "Present")
                html = html.replace("{{JOB_COMPANY}}", m["company"] or "")
                html = html.replace("{{EXPERIENCE_ITEMS}}", exp_items)
                html = html.replace("{{EDUCATION}}", education)
                out_html = os.path.join(gen_dir, f"{candidate.id}_{m['job_id']}.html")
                with open(out_html, "w", encoding="utf-8") as hf:
                    hf.write(html)
                resume_generated_html_url = f"/static/resumes_generated/{os.path.basename(out_html)}"
            except Exception:
                resume_generated_html_url = None
        else:
            resume_generated_html_url = None

        assigned.append({
            "job_id": m["job_id"],
            "title": m["title"],
            "company": m["company"],
            "match_score": m["match_score"],
            "application_id": application_id,
            "resume_generated": resume_generated_url,
            "resume_generated_html": resume_generated_html_url
        })

    return {
        "keywords_used": keywords,
        "new_jobs_pulled": new_jobs,
        "assigned_jobs": assigned,
        "matches_considered": len(matches)
    }


@router.post("/auto-pull-match-assign-all")
def auto_pull_match_assign_all(
    top_n: int = 5,
    min_score: int = 30,
    max_keywords: int = 10,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    candidates = db.query(models.Candidate).all()
    if not candidates:
        return {"message": "No candidates found", "assigned": []}

    keyword_set = []
    candidate_resume_skills = {}
    for candidate in candidates:
        skills = normalize_candidate_skills(candidate)
        resume_skills = []
        if candidate.resume_url and candidate.resume_url.startswith("/static/"):
            local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
            text = extract_resume_text(local_path)
            resume_skills = extract_skills_from_text(text)
        candidate_resume_skills[candidate.id] = resume_skills
        combined = skills + resume_skills
        if candidate.current_title:
            combined += [w.lower() for w in candidate.current_title.split() if len(w) > 3]
        for s in combined:
            if s and s not in keyword_set:
                keyword_set.append(s)

    new_jobs = 0
    for kw in keyword_set[:max_keywords]:
        new_jobs += pull_jobs_from_usa_portals(db, query=kw)

    assigned_results = []
    for candidate in candidates:
        extra_skills = candidate_resume_skills.get(candidate.id, [])
        matches = get_matched_jobs_for_candidate(db, candidate, min_score=min_score, top_n=top_n * 5, extra_skills=extra_skills)
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        select = matches[:top_n]

        assigned = []
        for m in select:
            existing = db.query(models.JobApplication).filter(
                models.JobApplication.candidate_id == candidate.id,
                models.JobApplication.job_id == m["job_id"]
            ).first()
            if existing:
                existing.status = "assigned"
                db.commit()
                application_id = existing.id
                status_value = "updated"
            else:
                app = models.JobApplication(candidate_id=candidate.id, job_id=m["job_id"], status="assigned")
                db.add(app); db.commit(); db.refresh(app)
                application_id = app.id
                status_value = "new"

            assigned.append({
                "job_id": m["job_id"],
                "title": m["title"],
                "company": m["company"],
                "match_score": m["match_score"],
                "application_id": application_id,
                "status": status_value
            })

        assigned_results.append({
            "candidate_id": candidate.id,
            "assigned_jobs": assigned,
            "matches_considered": len(matches)
        })

    return {
        "new_jobs_pulled": new_jobs,
        "keywords_used": keyword_set[:max_keywords],
        "assigned": assigned_results
    }


@router.get("/me/stats")
def get_my_stats(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["candidate"]))
):
    """Return job stats for the logged-in candidate."""
    candidate = db.query(models.Candidate).filter(
        models.Candidate.user_id == current_user.id
    ).first()
    if not candidate:
        return {
            "total_jobs": 0, "applied": 0, "assigned": 0,
            "interviewing": 0, "placed": 0, "match_count": 0
        }

    from sqlalchemy import func
    total_apps = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.candidate_id == candidate.id
    ).scalar()
    applied = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.candidate_id == candidate.id,
        models.JobApplication.status == "applied"
    ).scalar()
    assigned = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.candidate_id == candidate.id,
        models.JobApplication.status == "assigned"
    ).scalar()
    interviewing = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.candidate_id == candidate.id,
        models.JobApplication.status == "interviewing"
    ).scalar()
    placed = db.query(func.count(models.JobApplication.id)).filter(
        models.JobApplication.candidate_id == candidate.id,
        models.JobApplication.status == "placed"
    ).scalar()

    total_jobs = db.query(func.count(models.Job.id)).filter(models.Job.is_active == True).scalar()
    extra_skills = []
    if candidate.resume_url and candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        extra_skills = extract_skills_from_text(text)

    matches = get_matched_jobs_for_candidate(db, candidate, min_score=20, top_n=100, extra_skills=extra_skills)

    return {
        "total_jobs": total_jobs,
        "applied": applied,
        "assigned": assigned,
        "interviewing": interviewing,
        "placed": placed,
        "match_count": len(matches),
        "profile_complete": bool((candidate.skills or extra_skills) and candidate.current_title),
    }


@router.get("/", response_model=List[schemas.CandidateOut])
def get_all_candidates(
    skip: int = 0, limit: int = 50,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter"]))
):
    return db.query(models.Candidate).offset(skip).limit(limit).all()


@router.get("/{candidate_id}/job-matches")
def get_candidate_job_matches(
    candidate_id: int,
    min_score: int = 20,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.require_role(["admin", "recruiter", "candidate"]))
):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    # Candidates can only see their own
    role = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
    if role and role.role_name == "candidate" and candidate.user_id != current_user.id:
        raise HTTPException(403, "Forbidden")

    extra_skills = []
    if candidate.resume_url and candidate.resume_url.startswith("/static/"):
        local_path = os.path.join("uploads", candidate.resume_url.replace("/static/", ""))
        text = extract_resume_text(local_path)
        extra_skills = extract_skills_from_text(text)

    matches = get_matched_jobs_for_candidate(db, candidate, min_score=min_score, extra_skills=extra_skills)
    return {"candidate_id": candidate_id, "matches": matches}
