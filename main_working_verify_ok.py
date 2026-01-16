from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlmodel import select
import os
from PIL import Image, ImageDraw, ImageFont
import qrcode

from database import (
    create_db_and_tables,
    get_session,
    User,
    Attempt,
    Answer,
    Certificate,
)

app = FastAPI(title="IPS Photography Platform – Core")

# -----------------------------
# CONFIG
# -----------------------------
MCQ_MARK = 4
PASS_PERCENT = 50.0
CERT_DIR = "cert_previews"
os.makedirs(CERT_DIR, exist_ok=True)

# -----------------------------
# QUESTIONS
# -----------------------------
LEVEL1_QUESTIONS = [
    {
        "id": 1,
        "question": "Which element controls the amount of light entering the camera?",
        "options": {1: "ISO", 2: "Shutter Speed", 3: "Aperture", 4: "White Balance"},
        "correct_option": 3,
    },
    {
        "id": 2,
        "question": "Which setting controls image noise?",
        "options": {1: "ISO", 2: "Aperture", 3: "Focal Length", 4: "Focus Mode"},
        "correct_option": 1,
    },
    {
        "id": 3,
        "question": "Shutter speed mainly controls?",
        "options": {1: "Color", 2: "Motion blur", 3: "Sharpness", 4: "White balance"},
        "correct_option": 2,
    },
    {
        "id": 4,
        "question": "What does a low f-number indicate?",
        "options": {1: "Small aperture", 2: "Deep depth of field", 3: "Large aperture", 4: "Low ISO"},
        "correct_option": 3,
    },
    {
        "id": 5,
        "question": "Which triangle forms the exposure triangle?",
        "options": {
            1: "ISO, Aperture, Shutter Speed",
            2: "Focus, ISO, Zoom",
            3: "ISO, FPS, Aperture",
            4: "Shutter, Color, ISO",
        },
        "correct_option": 1,
    },
]

TOTAL_MARKS = len(LEVEL1_QUESTIONS) * MCQ_MARK

# -----------------------------
# MODELS
# -----------------------------
class AnswerItem(BaseModel):
    question_id: int
    selected_option_id: Optional[int]


class SubmitRequest(BaseModel):
    user_name: Optional[str]
    user_email: Optional[str]
    level: int
    answers: List[AnswerItem]


# -----------------------------
# STARTUP
# -----------------------------
@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# -----------------------------
# HEALTH
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# QUESTIONS
# -----------------------------
@app.get("/exam/level1/questions")
def get_questions():
    qs = []
    for q in LEVEL1_QUESTIONS:
        x = q.copy()
        x.pop("correct_option")
        qs.append(x)
    return {"level": 1, "questions": qs, "total_marks": TOTAL_MARKS}


# -----------------------------
# SUBMIT EXAM
# -----------------------------
@app.post("/exam/level1/submit")
def submit_exam(req: SubmitRequest):
    if req.level != 1:
        raise HTTPException(400, "Only Level-1 supported")

    score = 0
    qmap = {q["id"]: q for q in LEVEL1_QUESTIONS}

    with get_session() as session:
        user = session.exec(
            select(User).where(User.email == req.user_email)
        ).first() if req.user_email else None

        if not user:
            user = User(full_name=req.user_name, email=req.user_email)
            session.add(user)
            session.commit()
            session.refresh(user)

        attempt = Attempt(
            user_id=user.id,
            course_level=1,
            attempt_number=1,
            total_marks=TOTAL_MARKS,
            total_marks_obtained=0,
            percentage=0,
            grade="FAIL",
            is_passed=False,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        for a in req.answers:
            q = qmap.get(a.question_id)
            correct = q["correct_option"] if q else None
            marks = MCQ_MARK if a.selected_option_id == correct else 0
            score += marks

            session.add(
                Answer(
                    attempt_id=attempt.id,
                    question_id=a.question_id,
                    selected_option_id=a.selected_option_id,
                    correct_option=correct,
                    marks_awarded=marks,
                )
            )

        pct = (score / TOTAL_MARKS) * 100
        passed = pct >= PASS_PERCENT

        attempt.total_marks_obtained = score
        attempt.percentage = round(pct, 2)
        attempt.is_passed = passed
        attempt.grade = "PASS" if passed else "FAIL"

        cert_code = None

        if passed:
            cert = Certificate(
                user_id=user.id,
                course_level=1,
                attempt_id=attempt.id,
                certificate_code="TEMP",
                grade=attempt.grade,
                percentage=attempt.percentage,
            )
            session.add(cert)
            session.commit()
            session.refresh(cert)

            cert_code = f"IPS-{datetime.utcnow().year}-{cert.id:06d}"
            cert.certificate_code = cert_code
            session.add(cert)

        session.commit()

    return {
        "marks": score,
        "percentage": round(pct, 2),
        "passed": passed,
        "certificate_code": cert_code,
    }
# -----------------------------
# VERIFY CERTIFICATE
# -----------------------------
@app.get("/verify/{code}")
def verify_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(status_code=404, detail="Certificate not found")

        return {
            "certificate_code": cert.certificate_code,
            "grade": cert.grade,
            "percentage": cert.percentage,
            "issued_at": cert.issued_at
        }
