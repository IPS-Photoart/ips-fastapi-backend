from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlmodel import select
from typing import List, Optional
from datetime import datetime
import os

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
    allow_origins=["*"],  # frontend is GitHub Pages
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://ips-fastapi-backend.onrender.com"

# -------------------------------------------------
# STARTUP: CREATE TABLES + SEED CERTIFICATES
# -------------------------------------------------
@app.on_event("startup")
def startup():
    create_db_and_tables()
    seed_certificates()


# -------------------------------------------------
# SEED CERTIFICATE MASTER (CRITICAL)
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
# LIST CERTIFICATES (FOR DROPDOWN)
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
# EXAM QUESTIONS (PLACEHOLDER STRUCTURE)
# -------------------------------------------------
@app.get("/exam/{certificate_code}/questions")
def get_exam(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        return {
            "certificate": f"{cert.title} ({cert.abbreviation})",
            "duration_minutes": cert.duration_minutes,
            "mcq_count": cert.mcq_count,
            "short_answer_count": cert.short_answer_count,
            "mcq_mark": cert.mcq_mark,
            "pass_percentage": cert.pass_percentage,
            "questions": [],  # frontend renders dynamically
        }


# -------------------------------------------------
# EXAM SUBMISSION (UNLIMITED ATTEMPTS)
# -------------------------------------------------
@app.post("/exam/{certificate_code}/submit")
def submit_exam(
    certificate_code: str,
    user_name: str,
    user_email: Optional[str],
    marks_obtained: int,
):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        user = None
        if user_email:
            user = session.exec(
                select(User).where(User.email == user_email)
            ).first()

        if not user:
            user = User(full_name=user_name, email=user_email)
            session.add(user)
            session.commit()
            session.refresh(user)

        total_marks = cert.mcq_count * cert.mcq_mark
        percentage = (marks_obtained / total_marks) * 100
        passed = percentage >= cert.pass_percentage

        attempt = Attempt(
            user_id=user.id,
            certificate_code=cert.code,
            total_marks=total_marks,
            marks_obtained=marks_obtained,
            percentage=percentage,
            is_passed=passed,
        )
        session.add(attempt)
        session.commit()

        cert_code = None
        if passed:
            issued = Certificate(
                user_id=user.id,
                certificate_type_code=cert.code,
                certificate_code=f"IPS-{cert.code}-{attempt.id}",
                grade="PASS",
                percentage=percentage,
                is_paid=False,
                verification_url=f"{BASE_URL}/verify/IPS-{cert.code}-{attempt.id}",
            )
            session.add(issued)
            session.commit()
            cert_code = issued.certificate_code

        return {
            "passed": passed,
            "percentage": round(percentage, 2),
            "certificate_code": cert_code,
        }


# -------------------------------------------------
# VERIFY CERTIFICATE
# -------------------------------------------------
@app.get("/verify/{certificate_code}")
def verify(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Certificate not found")

        return {
            "certificate_code": cert.certificate_code,
            "percentage": cert.percentage,
            "issued_at": cert.issued_at,
            "paid": cert.is_paid,
        }
