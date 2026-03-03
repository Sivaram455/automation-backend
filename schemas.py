from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# Role Schemas
class RoleBase(BaseModel):
    role_name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    pass

class RoleOut(RoleBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

# User Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role_name: str = "candidate" # admin, recruiter, candidate

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

# Candidate Schemas
class CandidateBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    experience_years: Optional[int] = None
    current_title: Optional[str] = None
    skills: Optional[Any] = None
    resume_url: Optional[str] = None

class CandidateCreate(CandidateBase):
    pass

class CandidateOut(CandidateBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

# Job Schemas
class JobBase(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[Any] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    apply_url: Optional[str] = None
    source: Optional[str] = None

class JobCreate(JobBase):
    pass

class JobOut(JobBase):
    id: int
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

# Job Application Schemas
class JobApplicationBase(BaseModel):
    status: Optional[str] = "applied"

class JobApplicationCreate(JobApplicationBase):
    job_id: int

class JobApplicationOut(JobApplicationBase):
    id: int
    candidate_id: int
    job_id: int
    applied_at: datetime
    class Config:
        from_attributes = True
