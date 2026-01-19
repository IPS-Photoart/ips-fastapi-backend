from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from typing import Optional, List
from datetime import datetime

from database import (
    create_db_and_tables,
    get_session,
    User,
    CertificateType,
    Attempt,
    Certificate,
    Answer,
    Question,
    Option,
)

# -------------------------------------------------
# APP
# -------------------------------------------------
app = FastAPI(title="IPS Certification Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # GitHub Pages
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
# SEED CERTIFICATES (SAFE)
# -------------------------------------------------
def seed_certificates():
    certificates = [
        ("LEVEL-1","Level 1 – Basic Photography","L1-BP",30,25,0,4,50.0,
         "Exposure triangle, ISO, aperture, shutter speed"),
        ("LEVEL-2","Level 2 – Intermediate Composition & Lighting","L2-ICL",45,20,5,4,50.0,
         "High/low key, framing, positive & negative space"),
        ("LEVEL-3","Level 3 – Professional Photography Fundamentals Completion Certificate","L3-PPF",60,20,5,4,50.0,
         "Advanced analytical MCQs & short answers"),
        ("EPM-IWP","Elite Professional Master in Indian Wedding Photography","EPM-IWP",90,20,5,4,60.0,
         "Subject oriented, technical & practical field work"),
        ("EPM-EP","Elite Professional Master in Event Photography","EPM-EP",90,20,5,4,60.0,
         "Subject oriented, technical & practical field work"),
        ("EPM-CPP","Elite Professional Master in Commercial Product Photography","EPM-CPP",90,20,5,4,60.0,
         "Subject oriented, technical & practical field work"),
        ("EPM-WP","Elite Professional Master in Wildlife Photography","EPM-WP",90,20,5,4,60.0,
         "Subject oriented, technical & practical field work"),
    ]

    with get_session() as session:
        for c in certificates:
            if not session.exec(
                select(CertificateType).where(CertificateType.code == c[0])
            ).first():
                session.add(CertificateType(
                    code=c[0], title=c[1], abbreviation=c[2],
                    duration_minutes=c[3], mcq_count=c[4],
                    short_answer_count=c[5], mcq_mark=c[6],
                    pass_percentage=c[7], description=c[8]
                ))
        session.commit()

# -------------------------------------------------
# HEALTH
# -------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# CERTIFICATE LIST (DROPDOWN)
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
# LOAD EXAM QUESTIONS (DB-BASED)
# -------------------------------------------------
@app.get("/exam/{certificate_code}/questions")
def get_exam(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()
        if not cert:
            raise HTTPException(404, "Invalid certificate")

        questions_db = session.exec(
            select(Question).where(Question.certificate_code == certificate_code)
        ).all()

        questions = []
        for q in questions_db:
            if q.question_type == "MCQ":
                options = session.exec(
                    select(Option).where(Option.question_id == q.id)
                ).all()
                questions.append({
                    "id": q.id,
                    "question": q.question_text,
                    "options": [o.option_text for o in options],
                })
            else:
                questions.append({
                    "id": q.id,
                    "question": q.question_text,
                    "type": "SHORT",
                })

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
# SUBMIT EXAM (MCQs EVALUATED, SHORT STORED)
# -------------------------------------------------
@app.post("/exam/{certificate_code}/submit")
def submit_exam(
    certificate_code: str,
    payload: dict = Body(...)
):
    answers = payload.get("answers", [])

    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()
        if not cert:
            raise HTTPException(404, "Invalid certificate")

        total_marks = cert.mcq_count * cert.mcq_mark
        obtained = 0

        attempt = Attempt(
            user_id=0,  # anonymous for now
            certificate_code=certificate_code,
            total_marks=total_marks,
            marks_obtained=0,
            percentage=0,
            is_passed=False,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        for a in answers:
            q = session.get(Question, a["question_id"])
            if not q:
                continue

            marks = 0
            if q.question_type == "MCQ":
                opt = session.exec(
                    select(Option).where(
                        Option.question_id == q.id,
                        Option.option_text != None
                    )
                ).all()
                correct = next((o for o in opt if o.is_correct), None)
                if correct and a["selected_option"] == opt.index(correct) + 1:
                    marks = q.marks
                    obtained += marks

            session.add(Answer(
                attempt_id=attempt.id,
                question_id=q.id,
                answer_text=str(a.get("selected_option")),
                marks_awarded=marks
            ))

        percentage = (obtained / total_marks) * 100 if total_marks else 0
        passed = percentage >= cert.pass_percentage

        attempt.marks_obtained = obtained
        attempt.percentage = percentage
        attempt.is_passed = passed
        session.commit()

        return {
            "result": "PASS" if passed else "FAIL",
            "marks_obtained": obtained,
            "total_marks": total_marks,
            "percentage": round(percentage, 2),
        }

# -------------------------------------------------
# VERIFY CERTIFICATE (UNCHANGED)
# -------------------------------------------------
@app.get("/verify/{certificate_code}")
def verify(certificate_code: str):
    return {
        "certificate_code": certificate_code,
        "status": "Verification endpoint active",
    }
