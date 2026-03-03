from sqlalchemy import Boolean, Column, ForeignKey, String, Text, DateTime, func, JSON, Float, BigInteger, Integer
from sqlalchemy.orm import relationship
from database import Base

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(BigInteger, primary_key=True, index=True)
    role_name = Column(String(50), nullable=False, unique=True)
    description = Column(String(150))
    created_at = Column(DateTime, server_default=func.now())
    
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True, index=True)
    role_id = Column(BigInteger, ForeignKey("roles.id"), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    role = relationship("Role", back_populates="users")
    candidate = relationship("Candidate", back_populates="user", uselist=False)

class Candidate(Base):
    __tablename__ = "candidates"
    
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    location = Column(String(150))
    experience_years = Column(Integer)
    current_title = Column(String(150))
    skills = Column(JSON)
    resume_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="candidate")
    applications = relationship("JobApplication", back_populates="candidate")

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(BigInteger, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    company = Column(String(150))
    location = Column(String(150))
    job_type = Column(String(50))
    country = Column(String(50))
    description = Column(Text)
    skills = Column(JSON)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    apply_url = Column(Text)
    source = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    
    applications = relationship("JobApplication", back_populates="job")

class JobApplication(Base):
    __tablename__ = "job_applications"
    
    id = Column(BigInteger, primary_key=True, index=True)
    candidate_id = Column(BigInteger, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="applied")
    applied_at = Column(DateTime, server_default=func.now())
    
    candidate = relationship("Candidate", back_populates="applications")
    job = relationship("Job", back_populates="applications")
