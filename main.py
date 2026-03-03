from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

import models
from database import engine

models.Base.metadata.create_all(bind=engine)
logger.info("[OK] Connected to MySQL database and tables verified.")

from routers import auth, jobs, candidates, admin, assignments

app = FastAPI(
    title="JobPull API",
    description="Backend API for Job Pulling, Candidates, and Applications",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/static", StaticFiles(directory="uploads"), name="static")

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(admin.router)
app.include_router(assignments.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to JobPull Backend API v2.0", "status": "running"}


@app.get("/health")
def health_check():
    try:
        from database import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}
