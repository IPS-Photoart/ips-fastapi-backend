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

from email_credentials import (
    SMTP_EMAIL,
    SMTP_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
)

from certificate_engine import (
    generate_certificate_png,
    add_preview_watermark,
)

from email_service import send_certificate_email

# -------------------------------------------------
# APP
# -------------------------------------------------
app = FastAPI(title="IPS Automated Certification Platform")
app.mount("/static", StaticFiles(directory="static"), name="static")

BASE_URL = "https://ips-photoart.github.io"
CERT_DIR = "cert_previews"
os.makedirs(CERT_DIR, exist_ok=True)

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
        return session.exec(select(CertificateType)).all()

# -------------------------------------------------
# EXAM QUESTIONS
# -------------------------------------------------
@app.get("/exam/{certificate_code}/questions")
def get_exam_questions(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(CertificateType)
            .where(CertificateType.code == certificate_code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        questions = session.exec(
            select(Question)
            .where(Question.certificate_code == certificate_code)
        ).all()

        return {
            "certificate": cert.title,
            "total_questions": cert.total_questions,
            "mcq_mark": cert.mcq_mark,
            "pass_percentage": cert.pass_percentage,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options
                } for q in questions
            ]
        }

# -------------------------------------------------
# MODELS
# -------------------------------------------------
class AnswerItem(BaseModel):
    question_id: int
    selected_option_id: Optional[int]

class SubmitRequest(BaseModel):
    name: str
    email: str
    certificate_code: str
    answers: List[AnswerItem]

# -------------------------------------------------
# EXAM SUBMISSION
# -------------------------------------------------
@app.post("/exam/submit")
def submit_exam(req: SubmitRequest):
    with get_session() as session:
        cert_type = session.exec(
            select(CertificateType)
            .where(CertificateType.code == req.certificate_code)
        ).first()

        if not cert_type:
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
            select(Question)
            .where(Question.certificate_code == req.certificate_code)
        ).all()

        qmap = {q.id: q for q in questions}
        total_marks = cert_type.total_questions * cert_type.mcq_mark
        score = 0

        attempt = Attempt(
            user_id=user.id,
            certificate_code=req.certificate_code,
            total_marks=total_marks,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        for a in req.answers:
            q = qmap[a.question_id]
            marks = (
                cert_type.mcq_mark
                if a.selected_option_id == q.correct_option
                else 0
            )
            score += marks

            session.add(
                Answer(
                    attempt_id=attempt.id,
                    question_id=q.id,
                    selected_option_id=a.selected_option_id,
                    correct_option=q.correct_option,
                    marks_awarded=marks,
                )
            )

        percentage = (score / total_marks) * 100
        passed = percentage >= cert_type.pass_percentage

        attempt.total_marks_obtained = score
        attempt.percentage = round(percentage, 2)
        attempt.is_passed = passed
        attempt.grade = "PASS" if passed else "FAIL"

        session.add(attempt)
        session.commit()

        certificate_code = None
        if passed:
            cert = Certificate(
                user_id=user.id,
                certificate_code=f"IPS-{datetime.utcnow().year}-{attempt.id:06d}",
                certificate_type=req.certificate_code,
                percentage=attempt.percentage,
                grade=attempt.grade,
                is_paid=False,
            )
            session.add(cert)
            session.commit()
            certificate_code = cert.certificate_code

        return {
            "score": score,
            "percentage": round(percentage, 2),
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
            select(Certificate)
            .where(Certificate.certificate_code == code)
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
# CERTIFICATE DOWNLOAD
# -------------------------------------------------
@app.get("/certificate/{code}/download")
def download_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate)
            .where(Certificate.certificate_code == code)
        ).first()

        if not cert or not cert.is_paid:
            raise HTTPException(403, "Payment required")

        user = session.get(User, cert.user_id)

        img_path = generate_certificate_png(
            cert.certificate_code,
            user.full_name,
            cert.grade,
            cert.percentage,
            f"{BASE_URL}/verify/{code}",
        )

        return FileResponse(img_path, media_type="image/png")

# -------------------------------------------------
# PAYMENT CREATE
# -------------------------------------------------
@app.post("/payment/create/{certificate_code}")
def create_payment(certificate_code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate)
            .where(Certificate.certificate_code == certificate_code)
        ).first()

        if not cert or cert.is_paid:
            raise HTTPException(400, "Invalid payment")

        cert_type = session.exec(
            select(CertificateType)
            .where(CertificateType.code == cert.certificate_type)
        ).first()

        return razorpay_client.order.create({
            "amount": cert_type.certificate_fee * 100,
            "currency": "INR",
            "receipt": certificate_code,
            "notes": {"certificate_code": certificate_code},
        })

# -------------------------------------------------
# VERIFY CERTIFICATE
# -------------------------------------------------
@app.get("/verify/{code}")
def verify_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate)
            .where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(404, "Invalid certificate")

        return {
            "certificate_code": cert.certificate_code,
            "grade": cert.grade,
            "percentage": cert.percentage,
            "issued_at": cert.issued_at,
        }

# -------------------------------------------------
# RAZORPAY WEBHOOK
# -------------------------------------------------
@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid signature")

    payload = await request.json()

    if payload.get("event") == "payment.captured":
        code = payload["payload"]["payment"]["entity"]["notes"]["certificate_code"]

        with get_session() as session:
            cert = session.exec(
                select(Certificate)
                .where(Certificate.certificate_code == code)
            ).first()

            if cert and not cert.is_paid:
                cert.is_paid = True
                session.add(cert)
                session.commit()

                user = session.get(User, cert.user_id)
                send_certificate_email(user, cert)

    return {"status": "ok"}
