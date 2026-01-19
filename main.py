from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from typing import Optional
from datetime import datetime

from database import (
    create_db_and_tables,
    get_session,
    User,
    CertificateType,
    Attempt,
    Certificate,
)

# -------------------------------------------------
# APP
# -------------------------------------------------
app = FastAPI(title="IPS Certification Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # GitHub Pages frontend
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://ips-fastapi-backend.onrender.com"

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    create_db_and_tables()
    seed_certificates()

# -------------------------------------------------
# SEED CERTIFICATES
# -------------------------------------------------
def seed_certificates():
    certificates = [
        {
            "code": "LEVEL-1",
            "title": "Level 1 – Basic Photography",
            "abbreviation": "L1-BP",
            "duration_minutes": 30,
            "mcq_count": 25,
            "short_answer_count": 0,
            "mcq_mark": 4,
            "pass_percentage": 50.0,
            "description": "Exposure triangle, ISO, aperture, shutter speed",
        },
        {
            "code": "LEVEL-2",
            "title": "Level 2 – Intermediate Composition & Lighting",
            "abbreviation": "L2-ICL",
            "duration_minutes": 45,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 50.0,
            "description": "High/low key, framing, positive & negative space",
        },
        {
            "code": "LEVEL-3",
            "title": "Level 3 – Professional Photography Fundamentals Completion Certificate",
            "abbreviation": "L3-PPF",
            "duration_minutes": 60,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 50.0,
            "description": "Advanced analytical MCQs & short answers",
        },
        {
            "code": "EPM-IWP",
            "title": "Elite Professional Master in Indian Wedding Photography",
            "abbreviation": "EPM-IWP",
            "duration_minutes": 90,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 60.0,
            "description": "Subject oriented, technical & practical field work",
        },
        {
            "code": "EPM-EP",
            "title": "Elite Professional Master in Event Photography",
            "abbreviation": "EPM-EP",
            "duration_minutes": 90,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 60.0,
            "description": "Subject oriented, technical & practical field work",
        },
        {
            "code": "EPM-CPP",
            "title": "Elite Professional Master in Commercial Product Photography",
            "abbreviation": "EPM-CPP",
            "duration_minutes": 90,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 60.0,
            "description": "Subject oriented, technical & practical field work",
        },
        {
            "code": "EPM-WP",
            "title": "Elite Professional Master in Wildlife Photography",
            "abbreviation": "EPM-WP",
            "duration_minutes": 90,
            "mcq_count": 20,
            "short_answer_count": 5,
            "mcq_mark": 4,
            "pass_percentage": 60.0,
            "description": "Subject oriented, technical & practical field work",
        },
    ]

    with get_session() as session:
        for c in certificates:
            exists = session.exec(
                select(CertificateType).where(CertificateType.code == c["code"])
            ).first()
            if not exists:
                session.add(CertificateType(**c))
        session.commit()

# -------------------------------------------------
# HEALTH
# -------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# LIST CERTIFICATES
# -------------------------------------------------
@app.get("/certificates")
def list_certificates():
    with get_session() as session:
        certs = session.exec(select(CertificateType)).all()
        return [
            {
                "code": c.code,
                "title": f"{c.title} ({c.abbreviation})",
                "duration_minutes": c.duration_minutes,
                "mcq": c.mcq_count,
                "short_answers": c.short_answer_count,
            }
            for c in certs
        ]

# -------------------------------------------------
# LEVEL-1 MCQs + ANSWER KEY
# -------------------------------------------------
LEVEL_1_QUESTIONS = [
    {
        "id": 1,
        "question": "Which element controls the amount of light entering the camera?",
        "options": ["ISO", "Shutter Speed", "Aperture", "White Balance"],
    },
    {
        "id": 2,
        "question": "Which camera setting primarily controls image noise?",
        "options": ["Aperture", "ISO", "Shutter Speed", "Focal Length"],
    },
    {
        "id": 3,
        "question": "Shutter speed mainly affects which aspect of a photograph?",
        "options": ["Colour saturation", "Motion blur", "Lens sharpness", "Sensor size"],
    },
    {
        "id": 4,
        "question": "What does a lower f-number (e.g. f/1.8) indicate?",
        "options": ["Small aperture", "Large aperture", "Low ISO", "Slow shutter speed"],
    },
    {
        "id": 5,
        "question": "Which three elements form the exposure triangle?",
        "options": [
            "ISO, Aperture, Shutter Speed",
            "ISO, Focus, Zoom",
            "Aperture, White Balance, FPS",
            "Shutter Speed, Colour, ISO",
        ],
    },
]

LEVEL_1_ANSWER_KEY = {
    1: 3,
    2: 2,
    3: 2,
    4: 2,
    5: 1,
}

# -------------------------------------------------
# EXAM QUESTIONS
# -------------------------------------------------
@app.get("/exam/{certificate_code}/questions")
def get_exam(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        questions = LEVEL_1_QUESTIONS if certificate_code == "LEVEL-1" else []

        return {
            "certificate": f"{cert.title} ({cert.abbreviation})",
            "duration_minutes": cert.duration_minutes,
            "mcq_count": cert.mcq_count,
            "short_answer_count": cert.short_answer_count,
            "mcq_mark": cert.mcq_mark,
            "pass_percentage": cert.pass_percentage,
            "questions": questions,
        }

# -------------------------------------------------
# EXAM SUBMISSION (MCQ EVALUATION)
# -------------------------------------------------
@app.post("/exam/{certificate_code}/submit")
def submit_exam(certificate_code: str, payload: dict):
    answers = payload.get("answers", [])

    if certificate_code != "LEVEL-1":
        raise HTTPException(400, "Scoring not enabled for this certificate")

    total_questions = len(LEVEL_1_ANSWER_KEY)
    marks_per_question = 4
    total_marks = total_questions * marks_per_question

    obtained = 0
    for a in answers:
        qid = a.get("question_id")
        selected = a.get("selected_option")
        if LEVEL_1_ANSWER_KEY.get(qid) == selected:
            obtained += marks_per_question

    percentage = (obtained / total_marks) * 100
    passed = percentage >= 50.0

    return {
        "total_marks": total_marks,
        "marks_obtained": obtained,
        "percentage": round(percentage, 2),
        "result": "PASS" if passed else "FAIL",
    }

# -------------------------------------------------
# VERIFY CERTIFICATE (PLACEHOLDER)
# -------------------------------------------------
@app.get("/verify/{certificate_code}")
def verify(certificate_code: str):
    return {
        "certificate_code": certificate_code,
        "status": "Verification endpoint active",
    }
