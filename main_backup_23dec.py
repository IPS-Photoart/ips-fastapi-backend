from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
import razorpay
import hmac
import hashlib
import smtplib
from email.message import EmailMessage

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlmodel import select
import os
from PIL import Image, ImageDraw, ImageFont
import qrcode

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

from database import (
    create_db_and_tables,
    get_session,
    User,
    Attempt,
    Answer,
    Certificate,
)

app = FastAPI(title="IPS Photography Platform – Core")

# -------------------------------------------------
# GLOBAL CONFIG
# -------------------------------------------------
MCQ_MARK = 4
PASS_PERCENT = 50.0
CERT_DIR = "cert_previews"
CERTIFICATE_PRICE_RUPEES = 500

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
# QUESTIONS
# -------------------------------------------------
LEVEL1_QUESTIONS = [
    {"id": 1, "question": "Which element controls the amount of light entering the camera?",
     "options": {1: "ISO", 2: "Shutter Speed", 3: "Aperture", 4: "White Balance"}, "correct_option": 3},
    {"id": 2, "question": "Which setting controls image noise?",
     "options": {1: "ISO", 2: "Aperture", 3: "Focal Length", 4: "Focus Mode"}, "correct_option": 1},
    {"id": 3, "question": "Shutter speed mainly controls?",
     "options": {1: "Color", 2: "Motion blur", 3: "Sharpness", 4: "White balance"}, "correct_option": 2},
    {"id": 4, "question": "What does a low f-number indicate?",
     "options": {1: "Small aperture", 2: "Deep depth of field", 3: "Large aperture", 4: "Low ISO"}, "correct_option": 3},
    {"id": 5, "question": "Which triangle forms the exposure triangle?",
     "options": {1: "ISO, Aperture, Shutter Speed", 2: "Focus, ISO, Zoom",
                 3: "ISO, FPS, Aperture", 4: "Shutter, Color, ISO"}, "correct_option": 1},
]

TOTAL_MARKS = len(LEVEL1_QUESTIONS) * MCQ_MARK

# -------------------------------------------------
# MODELS
# -------------------------------------------------
class AnswerItem(BaseModel):
    question_id: int
    selected_option_id: Optional[int]

class SubmitRequest(BaseModel):
    user_name: Optional[str]
    user_email: Optional[str]
    level: int
    answers: List[AnswerItem]

# -------------------------------------------------
# EXAM FLOW
# -------------------------------------------------
@app.post("/exam/level1/submit")
def submit_exam(req: SubmitRequest):
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
            correct = qmap[a.question_id]["correct_option"]
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
                is_paid=False,
            )
            session.add(cert)
            session.commit()
            session.refresh(cert)

            cert_code = f"IPS-{datetime.utcnow().year}-{cert.id:06d}"
            cert.certificate_code = cert_code
            cert.verification_url = f"http://127.0.0.1:8000/verify/{cert_code}"
            session.add(cert)

        session.commit()

    return {
        "marks": score,
        "percentage": round(pct, 2),
        "passed": passed,
        "certificate_code": cert_code
    }

# -------------------------------------------------
# CERTIFICATE IMAGE
# -------------------------------------------------
def vertical_gradient(width, height, top_color, bottom_color):
    base = Image.new("RGB", (width, height), top_color)
    top = Image.new("RGB", (width, height), bottom_color)
    mask = Image.new("L", (width, height))
    for y in range(height):
        mask.putpixel((0, y), int(255 * (y / height)))
    mask = mask.resize((width, height))
    return Image.composite(top, base, mask)

def add_preview_watermark(img, text="PREVIEW – PAYMENT REQUIRED"):
    img = img.convert("RGBA")
    width, height = img.size
    text_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)

    try:
        font = ImageFont.truetype("arialbd.ttf", 64)
    except:
        font = ImageFont.load_default()

    for y in range(0, height, 450):
        for x in range(-width, width, 700):
            draw.text((x, y), text, font=font, fill=(150, 150, 150, 70))

    text_layer = text_layer.rotate(-30, expand=1)
    watermark = Image.new("RGBA", img.size, (255, 255, 255, 0))
    watermark = Image.alpha_composite(
        watermark,
        text_layer.crop((0, 0, width, height))
    )

    return Image.alpha_composite(img, watermark).convert("RGB")

def generate_certificate_png(cert_code, user_name, grade, percentage, verify_url):
    WIDTH, HEIGHT = 1650, 1150
    img = vertical_gradient(WIDTH, HEIGHT, (250, 244, 236), (232, 220, 205))
    draw = ImageDraw.Draw(img)

    # Banner
    banner = Image.open("banner.jpg")
    banner = banner.resize((WIDTH, int(WIDTH * banner.height / banner.width)))
    img.paste(banner, (0, 0))

    y_cursor = banner.height + 40

    # Logo
    logo = Image.open("logo.jpg").resize((180, 180))
    img.paste(logo, (100, y_cursor), logo if logo.mode == "RGBA" else None)

    try:
        title_font = ImageFont.truetype("arialbd.ttf", 48)
        body_font = ImageFont.truetype("arial.ttf", 30)
        small_font = ImageFont.truetype("arial.ttf", 22)
    except:
        title_font = body_font = small_font = ImageFont.load_default()

    draw.text(
        (WIDTH // 2, y_cursor + 20),
        "Indian Photographic Society",
        font=title_font,
        fill=(80, 50, 30),
        anchor="mm",
    )

    draw.text(
        (WIDTH // 2, y_cursor + 80),
        "Professional Photography Fundamentals – Completion Certificate",
        font=body_font,
        fill=(110, 80, 55),
        anchor="mm",
    )

    body_y = y_cursor + 170
    draw.text((350, body_y), "This is to certify that", font=body_font, fill=(60, 40, 20))
    draw.text((350, body_y + 45), user_name, font=title_font, fill=(40, 25, 15))
    draw.text(
        (350, body_y + 120),
        "has successfully completed the prescribed course and assessment.",
        font=body_font,
        fill=(60, 40, 20),
    )

    draw.text(
        (350, body_y + 190),
        f"Grade: {grade}     Score: {percentage}%",
        font=body_font,
        fill=(60, 40, 20),
    )

    draw.text(
        (350, body_y + 250),
        f"Certificate Code: {cert_code}",
        font=small_font,
        fill=(90, 60, 40),
    )

    # QR Code
    qr = qrcode.make(verify_url).resize((220, 220))
    img.paste(qr, (WIDTH - 360, HEIGHT - 360))

    draw.rectangle(
        (20, 20, WIDTH - 20, HEIGHT - 20),
        outline=(160, 120, 90),
        width=4,
    )

    path = os.path.join(CERT_DIR, f"{cert_code}.png")
    img.save(path)
    return path

# -------------------------------------------------
# CERTIFICATE ROUTES
# -------------------------------------------------
@app.get("/verify/{code}")
def verify_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(404, "Certificate not found")

        return {
            "certificate_code": cert.certificate_code,
            "grade": cert.grade,
            "percentage": cert.percentage,
            "issued_at": cert.issued_at,
        }

@app.get("/certificate/{code}/preview")
def preview_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(404, "Certificate not found")

        user = session.exec(
            select(User).where(User.id == cert.user_id)
        ).first()

        img_path = generate_certificate_png(
            cert.certificate_code,
            user.full_name if user else "Candidate",
            cert.grade,
            cert.percentage,
            cert.verification_url,
        )

        if not cert.is_paid:
            img = Image.open(img_path)
            img = add_preview_watermark(img)
            img.save(img_path)

    return FileResponse(img_path, media_type="image/png")

@app.get("/certificate/{code}/download")
def download_certificate(code: str):
    with get_session() as session:
        cert = session.exec(
            select(Certificate).where(Certificate.certificate_code == code)
        ).first()

        if not cert:
            raise HTTPException(404, "Certificate not found")

        if not cert.is_paid:
            raise HTTPException(403, "Payment required")

        user = session.exec(
            select(User).where(User.id == cert.user_id)
        ).first()

        img_path = generate_certificate_png(
            cert.certificate_code,
            user.full_name if user else "Candidate",
            cert.grade,
            cert.percentage,
            cert.verification_url,
        )

    return FileResponse(img_path, media_type="image/png")
