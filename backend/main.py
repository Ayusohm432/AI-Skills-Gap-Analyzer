from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time
import json
import os
import threading
import requests
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables (useful for local development runs without docker)
load_dotenv()

from database import analyses_collection, jobs_collection
from nlp.engine import (
    extract_text_from_pdf, 
    extract_skills_from_text, 
    match_role_and_skills, 
    generate_roadmap, 
    generate_interview_questions
)

app = FastAPI(title="AI Skill Gap Analyzer API", version="1.0.0")

def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    print("KeepAlive URL:", url)

    if not url:
        print("KeepAlive: RENDER_EXTERNAL_URL not found")
        return

    while True:
        try:
            requests.get(url, timeout=10)
            print("KeepAlive ping sent")
        except Exception as e:
            print("KeepAlive error:", e)

        time.sleep(600) 

@app.on_event("startup")
def startup_event():
    # This runs the keep_alive function in a background thread 
    # so it doesn't block your FastAPI server from handling real requests.
    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    
# Determine allowed origins dynamically
allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
production_url = os.getenv("FRONTEND_URL")

if production_url:
    # Remove any trailing slash and path to get just the protocol://domain
    parsed = urlparse(production_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in allowed_origins:
        allowed_origins.append(origin)
    # Also add the exact string just in case
    if production_url not in allowed_origins:
        allowed_origins.append(production_url)

print(f"CORS: Allowed Origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    target_role: str
    skills_detected: List[str]
    missing_skills: List[str]
    readiness_score: float
    roadmap: list
    interview_questions: List[str]

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "backend-api"}

@app.post("/api/v1/analyze/resume", response_model=AnalysisResponse)
async def analyze_resume(
    role: str = Form("Auto Detect"),
    resume: UploadFile = File(...)
):
    """
    Endpoint that accepts a file upload, parses text, and runs NLP analysis to find skill gaps.
    """
    if not resume:
        return AnalysisResponse(
            job_id="error", status="failed", target_role=role, 
            skills_detected=[], missing_skills=[], readiness_score=0, roadmap=[], interview_questions=[]
        )
        
    print(f"Received file: {resume.filename} for role {role}")
    
    # 1. Read bytes & Extract Text 
    file_bytes = await resume.read()
    raw_text = extract_text_from_pdf(file_bytes)

    # 2. AI NLP Extraction
    found_skills = extract_skills_from_text(raw_text)
    
    # 3. Role Comparison Logic
    # Fetch roles dynamically from the MongoDB jobs_collection
    cursor = jobs_collection.find({})
    db_roles = await cursor.to_list(length=100)
    
    roles_db = {}
    for r in db_roles:
        roles_db[r["role_name"]] = r["required_skills"]
        
    # Fallback to defaults if the database hasn't been seeded yet
    if not roles_db:
        roles_db = {
            "Data Scientist": ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"],
            "Machine Learning Engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"],
            "Backend Developer": ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"],
            "Frontend Developer": ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"],
            "Cyber Security Analyst": ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"]
        }
    
    analysis = match_role_and_skills(found_skills, roles_db, role)
    
    target_role = analysis["target_role"]
    readiness_score = analysis["readiness_score"]
    missing_skills = analysis["missing_skills"]
    identified_skills = analysis["identified_skills"]

    # 4. Generate Roadmaps and Qs
    roadmap = generate_roadmap(missing_skills)
    interview_qs = generate_interview_questions(missing_skills)

    # 5. Database Storage (MongoDB)
    document = {
        "user_id": "anonymous",
        "target_role": target_role,
        "readiness_score": readiness_score,
        "identified_skills": identified_skills,
        "missing_skills": missing_skills,
        "roadmap": roadmap,
        "interview_questions": interview_qs,
        "created_at": datetime.utcnow()
    }
    
    result = await analyses_collection.insert_one(document)

    return AnalysisResponse(
        job_id=str(result.inserted_id),
        status="completed",
        target_role=target_role,
        skills_detected=identified_skills,
        missing_skills=missing_skills,
        readiness_score=readiness_score,
        roadmap=roadmap,
        interview_questions=interview_qs
    )

@app.get("/api/v1/jobs/roles")
async def get_roles():
    """Returns canonical roles available in the system dynamically from the database"""
    cursor = jobs_collection.find({}, {"role_name": 1, "_id": 0})
    db_roles = await cursor.to_list(length=100)
    
    roles = [r["role_name"] for r in db_roles]
    
    # Always ensure Auto Detect is an option at the top
    if not roles:
         roles = [
            "Data Scientist",
            "Machine Learning Engineer",
            "Backend Developer",
            "Frontend Developer",
            "Cyber Security Analyst"
        ]
        
    return {
        "roles": ["Auto Detect"] + roles
    }
