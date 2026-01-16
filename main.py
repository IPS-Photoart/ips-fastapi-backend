from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import razorpay, hmac, hashlib, os
from PIL import Image

from database import (
    create_db_and_tables,
    get_session,
    User,
    Attempt,
    Answer,
    Certificate,
    CertificateType,
    Question,
)

from razorpay_credentials import (
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
)

from certificate_engine import (
    generate_certificate_png,
    add_preview_watermark,
)

from email_service import send_certificate_email

# -------------------------------------------------
# APP INIT
# -------------------------------------------------
app = FastAPI(title="IPS Automated Certification Platform")
app.mount("/static", StaticFiles(directory="static"), name="static")

BASE_URL = "https://ips-photoart.github.io"

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

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
        return session.exec(select(CertificateType).where(CertificateType.is_active == True)).all()

# -------------------------------------------------
# FETCH EXAM STRUCTURE + QUESTIONS
# -------------------------------------------------
@app.get("/exam/{certificate_code}/questions")
def get_exam_questions(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        questions = session.exec(
            select(Question).where(Question.certificate_code == certificate_code)
        ).all()

        return {
            "certificate": cert.title,
            "duration_minutes": cert.duration_minutes,
            "mcq_count": cert.mcq_count,
            "short_answer_count": cert.short_answer_count,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options if q.question_type == "MCQ" else None,
                    "question_type": q.question_type,
                    "max_marks": q.max_marks,
                }
                for q in questions
            ],
        }

# -------------------------------------------------
# MODELS
# -------------------------------------------------
class AnswerItem(BaseModel):
    question_id: int
    answer: Optional[str]   # MCQ option number OR short text

class SubmitRequest(BaseModel):
    name: str
    email: str
    certificate_code: str
    answers: List[AnswerItem]

# -------------------------------------------------
# AI SHORT ANSWER EVALUATION (BASIC)
# -------------------------------------------------
def ai_evaluate_short_answer(answer_text: str, max_marks: int) -> int:
    """
    Placeholder AI evaluator.
    Replace with OpenAI / LLM scoring later.
    """
    if not answer_text:
        return 0
    length_score = min(len(answer_text) // 50, max_marks)
    return max(1, length_score)

# -------------------------------------------------
# EXAM SUBMISSION
# -------------------------------------------------
@app.post("/exam/submit")
def submit_exam(req: SubmitRequest):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == req.certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        user = session.exec(
            select(User).where(User.email == req.email)
        ).first()

        if not user:
            user = User(full_name=req.name, email=req.email)
            session.add(user)
            session.commit()
            session.refresh(user)

        questions = session.exec(
            select(Question).where(Question.certificate_code == req.certificate_code)
        ).all()

        qmap = {q.id: q for q in questions}
        total_marks = sum(q.max_marks for q in questions)
        obtained_marks = 0

        attempt = Attempt(
            user_id=user.id,
            certificate_code=req.certificate_code,
            total_marks=total_marks,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        for a in req.answers:
            q = qmap.get(a.question_id)
            if not q:
                continue

            marks = 0

            if q.question_type == "MCQ":
                if str(a.answer) == str(q.correct_option):
                    marks = q.max_marks

            elif q.question_type == "SHORT":
                marks = ai_evaluate_short_answer(a.answer or "", q.max_marks)

            obtained_marks += marks

            session.add(
                Answer(
                    attempt_id=attempt.id,
                    question_id=q.id,
                    selected_option_id=a.answer,
                    correct_option=q.correct_option,
                    marks_awarded=marks,
                )
            )

        percentage = (obtained_marks / total_marks) * 100
        passed = percentage >= cert.pass_percentage

        attempt.total_marks_obtained = obtained_marks
        attempt.percentage = round(percentage, 2)
        attempt.is_passed = passed
        attempt.grade = "PASS" if passed else "FAIL"

        session.add(attempt)
        session.commit()

        certificate_code = None
        if passed:
            cert_row = Certificate(
                user_id=user.id,
                certificate_code=f"IPS-{datetime.utcnow().year}-{attempt.id:06d}",
                certificate_type=req.certificate_code,
                percentage=attempt.percentage,
                grade=attempt.grade,
                is_paid=False,
            )
            session.add(cert_row)
            session.commit()
            certificate_code = cert_row.certificate_code

        return {
            "score": obtained_marks,
            "percentage": attempt.percentage,
            "passed": passed,
            "certificate_code": certificate_code,
        }

# -------------------------------------------------
# CERTIFICATE PREVIEW
# -------------------------------------------------
@app.get("/certificate/{code}/preview")
def preview_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(404, "Certificate not found")

        user = session.get(User, cert.user_id)

        img_path = generate_certificate_png(
            cert.certificate_code,
            user.full_name,
            cert.grade,
            cert.percentage,
            f"{BASE_URL}/verify/{code}",
        )

        if not cert.is_paid:
            img = Image.open(img_path)
            img = add_preview_watermark(img)
            img.save(img_path)

        return FileResponse(img_path, media_type="image/png")

# -------------------------------------------------
# PAYMENT & WEBHOOK (UNCHANGED LOGIC)
# -------------------------------------------------
@app.post("/payment/create/{certificate_code}")
def create_payment(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == certificate_code)
        ).first()

        if not cert or cert.is_paid:
            raise HTTPException(400, "Invalid payment")

        cert_type = session.exec(
            select(CertificateType).where(CertificateType.code == cert.certificate_type)
        ).first()

        return razorpay_client.order.create({
            "amount": cert_type.certificate_fee * 100,
            "currency": "INR",
            "receipt": certificate_code,
            "notes": {"certificate_code": certificate_code},
        })
