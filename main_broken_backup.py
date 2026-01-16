from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from sqlmodel import select
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

# -----------------------------
# LEVEL-1 QUESTIONS (PASTE YOUR 25 HERE)
# -----------------------------
LEVEL1_QUESTIONS = [
    {
        "id": 1,
        "question": "Which element controls the amount of light entering the camera?",
        "options": {
            1: "ISO",
            2: "Shutter Speed",
            3: "Aperture",
            4: "White Balance"
        },
        "correct_option": 3
    },
    {
        "id": 2,
        "question": "Which setting controls image noise?",
        "options": {
            1: "ISO",
            2: "Aperture",
            3: "Focal Length",
            4: "Focus Mode"
        },
        "correct_option": 1
    },
    {
        "id": 3,
        "question": "Shutter speed mainly controls?",
        "options": {
            1: "Color",
            2: "Motion blur",
            3: "Sharpness",
            4: "White balance"
        },
        "correct_option": 2
    },
    {
        "id": 4,
        "question": "What does a low f-number indicate?",
        "options": {
            1: "Small aperture",
            2: "Deep depth of field",
            3: "Large aperture",
            4: "Low ISO"
        },
        "correct_option": 3
    },
    {
        "id": 5,
        "question": "Which triangle forms the exposure triangle?",
        "options": {
            1: "ISO, Aperture, Shutter Speed",
            2: "Focus, ISO, Zoom",
            3: "ISO, FPS, Aperture",
            4: "Shutter, Color, ISO"
        },
        "correct_option": 1
    },
    {
        "id": 6,
        "question": "High ISO usually results in?",
        "options": {
            1: "Sharper image",
            2: "More noise",
            3: "Lower exposure",
            4: "Better color"
        },
        "correct_option": 2
    },
    {
        "id": 7,
        "question": "Which mode gives full manual control?",
        "options": {
            1: "Auto",
            2: "Aperture Priority",
            3: "Shutter Priority",
            4: "Manual"
        },
        "correct_option": 4
    }
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
# GET QUESTIONS
# -----------------------------
@app.get("/exam/level1/questions")
def get_questions():
    qs = []
    for q in LEVEL1_QUESTIONS:
        qc = q.copy()
        qc.pop("correct_option", None)
        qs.append(qc)
    return {"level": 1, "questions": qs, "total_marks": TOTAL_MARKS}

# -----------------------------
# SUBMIT EXAM
# -----------------------------
@app.post("/exam/level1/submit")
def submit_exam(req: SubmitRequest):
    if req.level != 1:
        raise HTTPException(400, "Only Level-1 supported")

    qmap = {q["id"]: q for q in LEVEL1_QUESTIONS}
    score = 0

    with get_session() as session:
        # user
        user = None
        if req.user_email:
            user = session.exec(
                select(User).where(User.email == req.user_email)
            ).first()
        if not user:
            user = User(full_name=req.user_name, email=req.user_email)
            session.add(user)
            session.commit()
            session.refresh(user)

        # attempt count
        prev = session.exec(
            select(Attempt).where(
                Attempt.user_id == user.id,
                Attempt.course_level == 1,
            )
        ).all()

        attempt = Attempt(
            user_id=user.id,
            course_level=1,
            attempt_number=len(prev) + 1,
            total_marks=TOTAL_MARKS,
            total_marks_obtained=0,
            percentage=0,
            grade="FAIL",
            is_passed=False,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        # answers
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

        # finalise
        pct = (score / TOTAL_MARKS) * 100 if TOTAL_MARKS else 0
        passed = pct >= PASS_PERCENT

        attempt.total_marks_obtained = score
        attempt.percentage = round(pct, 2)
        attempt.is_passed = passed
        attempt.grade = "PASS" if passed else "FAIL"
        session.add(attempt)

        cert_code = None
        verify_url = None

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
            cert.verification_url = f"http://127.0.0.1:8000/verify/{cert_code}"
            session.add(cert)

        session.commit()

    return {
        "marks": score,
        "percentage": round(pct, 2),
        "passed": passed,
        "certificate_code": cert_code,
        "verification_url": verify_url,
    }
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os

CERT_DIR = "cert_previews"
os.makedirs(CERT_DIR, exist_ok=True)

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

    watermark = Image.new("RGBA", img.size, (255, 255, 255, 0))
    text_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)

    try:
        font = ImageFont.truetype("arialbd.ttf", 64)
    except:
        font = ImageFont.load_default()

    step_x = 700
    step_y = 450
    angle = -30

    for y in range(0, height + step_y, step_y):
        for x in range(-width, width + step_x, step_x):
            draw.text(
                (x, y),
                text,
                font=font,
                fill=(150, 150, 150, 60),
            )

    text_layer = text_layer.rotate(angle, expand=1)
    watermark = Image.alpha_composite(
        watermark,
        text_layer.crop((0, 0, width, height))
    )

    return Image.alpha_composite(img, watermark).convert("RGB")


def generate_certificate_png(
    cert_code,
    user_name,
    grade,
    percentage,
    verify_url,
    certificate_title="Professional Photography Fundamentals – Completion Certificate"
):
    WIDTH, HEIGHT = 1650, 1150

    img = vertical_gradient(
        WIDTH,
        HEIGHT,
        (250, 244, 236),
        (232, 220, 205)
    )
    draw = ImageDraw.Draw(img)

    banner = Image.open("banner.jpg")
    banner_ratio = banner.height / banner.width
    banner_height = int(WIDTH * banner_ratio)
    banner = banner.resize((WIDTH, banner_height))
    img.paste(banner, (0, 0))

    y_cursor = banner_height + 40

    logo = Image.open("logo.jpg").resize((180, 180))
    img.paste(logo, (100, y_cursor), logo if logo.mode == "RGBA" else None)

    try:
        title_font = ImageFont.truetype("arialbd.ttf", 48)
        subtitle_font = ImageFont.truetype("arial.ttf", 32)
        body_font = ImageFont.truetype("arial.ttf", 30)
        small_font = ImageFont.truetype("arial.ttf", 22)
    except:
        title_font = subtitle_font = body_font = small_font = ImageFont.load_default()

    center_x = WIDTH // 2
    draw.text((center_x, y_cursor + 20), "Indian Photographic Society",
              font=title_font, fill=(80, 50, 30), anchor="mm")

    draw.text((center_x, y_cursor + 70), certificate_title,
              font=subtitle_font, fill=(110, 80, 55), anchor="mm")

    draw.line((350, y_cursor + 115, WIDTH - 350, y_cursor + 115),
              fill=(150, 110, 80), width=2)

    body_y = y_cursor + 160
    draw.text((350, body_y), "This is to certify that", font=body_font, fill=(60, 40, 20))
    draw.text((350, body_y + 50), user_name, font=title_font, fill=(40, 25, 15))
    draw.text((350, body_y + 120),
              "has successfully completed the prescribed course and assessment.",
              font=body_font, fill=(60, 40, 20))
    draw.text((350, body_y + 190),
              f"Grade Awarded: {grade}        Score: {percentage}%",
              font=body_font, fill=(60, 40, 20))

    draw.text((350, body_y + 250),
              f"Certificate Code: {cert_code}",
              font=small_font, fill=(90, 60, 40))

    qr = qrcode.make(verify_url or "").resize((220, 220))
    img.paste(qr, (WIDTH - 360, HEIGHT - 360))

    draw.rectangle((20, 20, WIDTH - 20, HEIGHT - 20),
                   outline=(160, 120, 90), width=4)

    path = os.path.join(CERT_DIR, f"{cert_code}.png")
    img.save(path)
    return path
