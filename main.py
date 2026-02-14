from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from typing import List
from database import (
    create_db_and_tables,
    get_session,
    CertificateType,
    Question,
    Option,
    Attempt,
    Answer,
)

app = FastAPI(title="IPS Certification Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# STARTUP
# --------------------
@app.on_event("startup")
def startup():
    create_db_and_tables()
    seed_certificates()
    seed_level1_questions()


# --------------------
# CERTIFICATE SEED
# --------------------
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


# --------------------
# LEVEL 1 QUESTION SEED
# --------------------
def seed_level1_questions():
    data = [
        ("Which element controls the amount of light entering the camera?",
         ["ISO","Shutter Speed","Aperture","White Balance"], 3),
        ("Which camera setting primarily controls image noise?",
         ["Aperture","ISO","Shutter Speed","Focal Length"], 2),
        ("Shutter speed mainly affects which aspect of a photograph?",
         ["Colour saturation","Motion blur","Lens sharpness","Sensor size"], 2),
        ("What does a lower f-number (e.g. f/1.8) indicate?",
         ["Small aperture","Large aperture","Low ISO","Slow shutter speed"], 2),
        ("Which three elements form the exposure triangle?",
         ["ISO, Aperture, Shutter Speed","ISO, Focus, Zoom",
          "Aperture, White Balance, FPS","Shutter Speed, Colour, ISO"], 1),
    ]

    with get_session() as session:
        exists = session.exec(
            select(Question).where(Question.certificate_code == "LEVEL-1")
        ).first()

        if exists:
            return

        for qtext, options, correct in data:
            q = Question(
                certificate_code="LEVEL-1",
                question_text=qtext,
                correct_option=correct,
            )
            session.add(q)
            session.commit()
            session.refresh(q)

            for opt in options:
                session.add(Option(question_id=q.id, option_text=opt))

        session.commit()


# --------------------
# HEALTH
# --------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------
# CERTIFICATE LIST
# --------------------
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


# --------------------
# LOAD QUESTIONS
# --------------------
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
            options = session.exec(
                select(Option).where(Option.question_id == q.id)
            ).all()
            questions.append({
                "id": q.id,
                "question": q.question_text,
                "options": [o.option_text for o in options],
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


# --------------------
# SUBMIT EXAM
# --------------------
@app.post("/exam/{certificate_code}/submit")
def submit_exam(certificate_code: str, payload: dict = Body(...)):
    answers = payload.get("answers", [])

    with get_session() as session:
        cert = session.exec(
            select(CertificateType).where(CertificateType.code == certificate_code)
        ).first()
        if not cert:
            raise HTTPException(404, "Invalid certificate")

        questions = session.exec(
            select(Question).where(Question.certificate_code == certificate_code)
        ).all()

        total_marks = len(questions) * cert.mcq_mark
        obtained = 0

        attempt = Attempt(
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
            if a.get("selected_option") == q.correct_option:
                marks = cert.mcq_mark
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
