import models
from sqlalchemy.orm import Session
import requests
import logging
import os
from typing import Optional, List

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Free / open-source job APIs (no API key needed)
# ──────────────────────────────────────────────────────────────────────────────

SKILL_KEYWORDS = [
    "python", "sql", "data analysis", "machine learning", "react", "react.js",
    "java", "javascript", "typescript", "node", "node.js", "aws", "azure", "gcp",
    "devops", "product manager", "business analyst", "data engineer",
    "software engineer", "fullstack", "cybersecurity", "cloud", "django",
    "fastapi", "flask", "power bi", "tableau", "excel", "spark", "kafka",
    "kubernetes", "docker", "terraform", "golang", "rust", "c#", "c++", ".net",
    "postgresql", "mongodb", "mysql", "redis", "pytorch", "tensorflow", "git"
]


def _normalize_skills(text: str) -> list:
    """Extract known skills from job title + description text."""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        if skill in text_lower and skill not in found:
            found.append(skill.title())
    return found


def extract_skills_from_text(text: str) -> list:
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        if skill in text_lower and skill not in found:
            found.append(skill)
    return found


def extract_resume_text(resume_path: str) -> str:
    if not resume_path or not os.path.exists(resume_path):
        return ""
    ext = resume_path.lower().split(".")[-1]
    if ext == "txt":
        try:
            with open(resume_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""
    if ext in ["docx", "doc"]:
        try:
            from docx import Document
        except Exception:
            Document = None
        if Document is None:
            return ""
        try:
            doc = Document(resume_path)
            return "\n".join([p.text for p in doc.paragraphs])
        except Exception:
            return ""
    if ext == "pdf":
        try:
            from pdfminer.high_level import extract_text as pdf_extract_text
        except Exception:
            pdf_extract_text = None
        if pdf_extract_text is None:
            return ""
        try:
            return pdf_extract_text(resume_path) or ""
        except Exception:
            return ""
    return ""


def normalize_candidate_skills(candidate: models.Candidate, extra_skills: Optional[List[str]] = None) -> list:
    candidate_skills = []
    if candidate.skills:
        if isinstance(candidate.skills, list):
            candidate_skills = [str(s).lower() for s in candidate.skills]
        elif isinstance(candidate.skills, str):
            candidate_skills = [s.strip().lower() for s in candidate.skills.split(",")]
    if extra_skills:
        candidate_skills += [str(s).lower() for s in extra_skills]
    candidate_skills = [s for s in candidate_skills if s]
    return list(dict.fromkeys(candidate_skills))


def _pull_remotive(query: str = "") -> list:
    """Pull remote jobs from Remotive (free, no key)."""
    jobs = []
    try:
        url = "https://remotive.com/api/remote-jobs"
        params = {"limit": 50}
        if query:
            params["search"] = query
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get("jobs", [])
            for j in data:
                skills = _normalize_skills((j.get("title", "") + " " + j.get("tags", []).__str__()))
                # also pull from tags field
                tags = j.get("tags", [])
                if isinstance(tags, list):
                    for t in tags:
                        if t and t.title() not in skills:
                            skills.append(t.title())
                jobs.append({
                    "title": j.get("title", ""),
                    "company": j.get("company_name", ""),
                    "location": j.get("candidate_required_location") or "Remote",
                    "job_type": "remote",
                    "country": "USA",
                    "description": (j.get("description") or "")[:2000],
                    "skills": skills,
                    "source": "remotive",
                    "apply_url": j.get("url", ""),
                    "salary_min": None,
                    "salary_max": None,
                })
    except Exception as e:
        logger.warning(f"Remotive pull failed: {e}")
    return jobs


def _pull_the_muse(query: str = "") -> list:
    """Pull jobs from The Muse (free, no key needed for basic access)."""
    jobs = []
    try:
        url = "https://www.themuse.com/api/public/jobs"
        params = {"page": 0, "descending": "true"}
        if query:
            params["category"] = query
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get("results", [])
            for j in data[:40]:
                location = ""
                locs = j.get("locations", [])
                if locs:
                    location = locs[0].get("name", "")
                levels = j.get("levels", [])
                job_type = "full-time"
                if levels:
                    job_type = levels[0].get("name", "full-time").lower()
                title = j.get("name", "")
                company = j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else ""
                skills = _normalize_skills(title)
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or "USA",
                    "job_type": job_type,
                    "country": "USA",
                    "description": (j.get("contents") or "")[:2000],
                    "skills": skills,
                    "source": "the_muse",
                    "apply_url": j.get("refs", {}).get("landing_page", ""),
                    "salary_min": None,
                    "salary_max": None,
                })
    except Exception as e:
        logger.warning(f"The Muse pull failed: {e}")
    return jobs


def _pull_working_nomads(query: str = "developer") -> list:
    """Pull jobs from Working Nomads (free RSS/JSON)."""
    jobs = []
    try:
        url = f"https://www.workingnomads.com/api/exposed_jobs/?category={query}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                for j in data[:30]:
                    skills = _normalize_skills(j.get("title", "") + " " + (j.get("description") or ""))
                    jobs.append({
                        "title": j.get("title", ""),
                        "company": j.get("company", ""),
                        "location": j.get("region") or "Remote",
                        "job_type": "remote",
                        "country": "USA",
                        "description": (j.get("description") or "")[:2000],
                        "skills": skills,
                        "source": "working_nomads",
                        "apply_url": j.get("url", ""),
                        "salary_min": None,
                        "salary_max": None,
                    })
    except Exception as e:
        logger.warning(f"Working Nomads pull failed: {e}")
    return jobs


def _pull_ziprecruiter(query: str = "") -> list:
    key = os.getenv("ZIPRECRUITER_API_KEY")
    if not key:
        return []
    jobs = []
    try:
        url = "https://api.ziprecruiter.com/jobs/v1"
        params = {
            "api_key": key,
            "search": query or "developer",
            "location": "United States",
            "radius_miles": 500,
            "jobs_per_page": 50,
            "days_ago": 14,
        }
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 200:
            data = r.json().get("jobs", [])
            for j in data:
                title = j.get("name") or j.get("title") or ""
                company = j.get("hiring_company", {}).get("name") if isinstance(j.get("hiring_company"), dict) else (j.get("company") or "")
                city = j.get("city") or ""
                state = j.get("state") or ""
                location = ", ".join([p for p in [city, state] if p]).strip() or "USA"
                desc = j.get("snippet") or j.get("job_description") or ""
                skills = _normalize_skills(f"{title} {desc}")
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_type": j.get("employment_type") or "full-time",
                    "country": "USA",
                    "description": (desc or "")[:2000],
                    "skills": skills,
                    "source": "ziprecruiter",
                    "apply_url": j.get("url") or j.get("apply_url") or "",
                    "salary_min": j.get("salary_min"),
                    "salary_max": j.get("salary_max"),
                })
    except Exception as e:
        logger.warning(f"ZipRecruiter pull failed: {e}")
    return jobs


def _pull_jsearch_by_domain(
    domain: str,
    query: str = "",
    country: str = "us",
    date_posted: str = "all",
    num_pages: int = 1
) -> list:
    key = os.getenv("JSEARCH_RAPIDAPI_KEY")
    host = os.getenv("JSEARCH_RAPIDAPI_HOST", "jsearch.p.rapidapi.com")
    if not key:
        return []
    jobs = []
    try:
        url = f"https://{host}/search"
        q = query or ""
        q = (q + " ").strip() + f"site:{domain}"
        params = {
            "query": q,
            "page": 1,
            "num_pages": max(1, int(num_pages)),
            "country": country,
            "date_posted": date_posted
        }
        headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}
        r = requests.get(url, params=params, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json().get("data", []) or r.json().get("results", []) or []
            for j in data:
                title = j.get("job_title") or j.get("title") or ""
                company = j.get("employer_name") or j.get("company_name") or j.get("company") or ""
                city = j.get("job_city") or j.get("city") or ""
                state = j.get("job_state") or j.get("state") or ""
                country = j.get("job_country") or j.get("country") or "USA"
                location = ", ".join([p for p in [city, state] if p]).strip() or country
                desc = j.get("job_description") or j.get("description") or ""
                apply_url = j.get("job_apply_link") or j.get("job_apply_url") or j.get("apply_link") or j.get("url") or ""
                skills = _normalize_skills(f"{title} {desc}")
                src = "indeed" if "indeed" in domain else "glassdoor" if "glassdoor" in domain else "ziprecruiter" if "ziprecruiter" in domain else "jsearch"
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or country,
                    "job_type": j.get("job_employment_type") or j.get("employment_type") or "full-time",
                    "country": country or "USA",
                    "description": (desc or "")[:2000],
                    "skills": skills,
                    "source": src,
                    "apply_url": apply_url,
                    "salary_min": j.get("salary_min") or j.get("min_salary"),
                    "salary_max": j.get("salary_max") or j.get("max_salary"),
                })
    except Exception as e:
        logger.warning(f"JSearch pull for {domain} failed: {e}")
    return jobs


def _pull_jsearch(
    query: str = "",
    country: str = "us",
    date_posted: str = "all",
    num_pages: int = 1
) -> list:
    key = os.getenv("JSEARCH_RAPIDAPI_KEY")
    host = os.getenv("JSEARCH_RAPIDAPI_HOST", "jsearch.p.rapidapi.com")
    if not key:
        return []
    jobs = []
    try:
        url = f"https://{host}/search"
        params = {
            "query": query or "developer",
            "page": 1,
            "num_pages": max(1, int(num_pages)),
            "country": country,
            "date_posted": date_posted,
        }
        headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}
        r = requests.get(url, params=params, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json().get("data", []) or r.json().get("results", []) or []
            for j in data:
                title = j.get("job_title") or j.get("title") or ""
                company = j.get("employer_name") or j.get("company_name") or j.get("company") or ""
                city = j.get("job_city") or j.get("city") or ""
                state = j.get("job_state") or j.get("state") or ""
                country_val = j.get("job_country") or j.get("country") or "USA"
                location = ", ".join([p for p in [city, state] if p]).strip() or country_val
                desc = j.get("job_description") or j.get("description") or ""
                apply_url = j.get("job_apply_link") or j.get("job_apply_url") or j.get("apply_link") or j.get("url") or ""
                skills = _normalize_skills(f"{title} {desc}")
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or country_val,
                    "job_type": j.get("job_employment_type") or j.get("employment_type") or "full-time",
                    "country": country_val,
                    "description": (desc or "")[:2000],
                    "skills": skills,
                    "source": "jsearch",
                    "apply_url": apply_url,
                    "salary_min": j.get("salary_min") or j.get("min_salary"),
                    "salary_max": j.get("salary_max") or j.get("max_salary"),
                })
    except Exception as e:
        logger.warning(f"JSearch pull failed: {e}")
    return jobs


def pull_jobs_from_usa_portals(db: Session, query: str = "") -> int:
    """
    Pull jobs from multiple free open-source portals and store in DB.
    Sources: Remotive, The Muse, Working Nomads
    Returns: number of new jobs added
    """
    all_jobs = []

    # Pull from all sources
    all_jobs += _pull_remotive(query)
    all_jobs += _pull_the_muse(query)
    all_jobs += _pull_working_nomads(query or "developer")

    all_jobs += _pull_ziprecruiter(query)
    all_jobs += _pull_jsearch_by_domain("indeed.com", query, country="us", date_posted="all", num_pages=1)
    all_jobs += _pull_jsearch_by_domain("glassdoor.com", query, country="us", date_posted="all", num_pages=1)
    all_jobs += _pull_jsearch_by_domain("ziprecruiter.com", query, country="us", date_posted="all", num_pages=1)
    all_jobs += _pull_jsearch(query, country="us", date_posted="all", num_pages=1)

    logger.info(f"Fetched {len(all_jobs)} total jobs from all portals")

    jobs_added = 0
    for job_data in all_jobs:
        if not job_data.get("title"):
            continue
        # Dedup by title + company
        existing = db.query(models.Job).filter(
            models.Job.title == job_data["title"],
            models.Job.company == job_data["company"]
        ).first()

        if not existing:
            new_job = models.Job(
                title=job_data["title"],
                company=job_data.get("company"),
                location=job_data.get("location"),
                job_type=job_data.get("job_type"),
                country=job_data.get("country", "USA"),
                description=job_data.get("description"),
                skills=job_data.get("skills", []),
                source=job_data.get("source"),
                apply_url=job_data.get("apply_url"),
                salary_min=job_data.get("salary_min"),
                salary_max=job_data.get("salary_max"),
                is_active=True,
            )
            db.add(new_job)
            jobs_added += 1

    db.commit()
    logger.info(f"Added {jobs_added} new jobs to DB")
    return jobs_added


# ──────────────────────────────────────────────────────────────────────────────
# Skill-based matching
# ──────────────────────────────────────────────────────────────────────────────

def compute_match_score(candidate: models.Candidate, job: models.Job, extra_skills: Optional[List[str]] = None) -> int:
    """Score 0–100 based on skill overlap, title match, experience."""
    score = 0

    # Normalize candidate skills
    candidate_skills = normalize_candidate_skills(candidate, extra_skills)

    # Normalize job skills
    job_skills = []
    if job.skills:
        if isinstance(job.skills, list):
            job_skills = [str(s).lower() for s in job.skills]
        elif isinstance(job.skills, str):
            job_skills = [s.strip().lower() for s in job.skills.split(",")]

    # Skill overlap – up to 70 pts
    if job_skills:
        matched = sum(
            1 for js in job_skills
            if any(js in cs or cs in js for cs in candidate_skills)
        )
        score += int((matched / len(job_skills)) * 70)
    else:
        # fallback: check title keywords vs candidate skills
        title_words = (job.title or "").lower().split()
        matched_title = sum(1 for tw in title_words if any(tw in cs for cs in candidate_skills))
        if matched_title > 0:
            score += 30

    # Title match – up to 15 pts
    if candidate.current_title and job.title:
        title_words = job.title.lower().split()
        if any(w in (candidate.current_title or "").lower() for w in title_words if len(w) > 3):
            score += 15

    # Experience – up to 15 pts
    if candidate.experience_years is not None:
        exp = candidate.experience_years
        if exp >= 5:
            score += 15
        elif exp >= 2:
            score += 10
        else:
            score += 5

    return min(score, 100)


def get_matched_jobs_for_candidate(db: Session, candidate: models.Candidate, min_score: int = 20, top_n: int = 50, extra_skills: Optional[List[str]] = None) -> list:
    """Return top matching jobs for a candidate sorted by match score."""
    jobs = db.query(models.Job).filter(models.Job.is_active == True).all()
    scored = []
    for j in jobs:
        score = compute_match_score(candidate, j, extra_skills=extra_skills)
        if score >= min_score:
            scored.append({
                "job_id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "job_type": j.job_type,
                "skills": j.skills if isinstance(j.skills, list) else [],
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "apply_url": j.apply_url,
                "source": j.source,
                "description": (j.description or "")[:300],
                "match_score": score,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            })
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:top_n]
