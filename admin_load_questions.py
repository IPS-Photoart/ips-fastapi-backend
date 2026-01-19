print("SCRIPT STARTED")

from database import (
    get_session,
    create_db_and_tables,
    Question,
    Option,
)


# --------------------
# QUESTIONS DATA
# --------------------
QUESTIONS = {
    "LEVEL-1": [
        (
            "Which element controls the amount of light entering the camera?",
            ["ISO", "Shutter Speed", "Aperture", "White Balance"],
            3,
        ),
        (
            "Which camera setting primarily controls image noise?",
            ["Aperture", "ISO", "Shutter Speed", "Focal Length"],
            2,
        ),
        (
            "Shutter speed mainly affects which aspect of a photograph?",
            ["Colour saturation", "Motion blur", "Lens sharpness", "Sensor size"],
            2,
        ),
        (
            "What does a lower f-number indicate?",
            ["Small aperture", "Large aperture", "Low ISO", "Slow shutter speed"],
            2,
        ),
        (
            "Which three elements form the exposure triangle?",
            [
                "ISO, Aperture, Shutter Speed",
                "ISO, Focus, Zoom",
                "Aperture, White Balance, FPS",
                "Shutter Speed, Colour, ISO",
            ],
            1,
        ),
    ]
}

# --------------------
# LOAD QUESTIONS
# --------------------
def load():
    create_db_and_tables()   # <-- ADD THIS LINE
    with get_session() as session:
        for cert, qs in QUESTIONS.items():
            for qtext, options, correct in qs:
                q = Question(
                    certificate_code=cert,
                    question_text=qtext,
                    correct_option=correct,
                )
                session.add(q)
                session.commit()
                session.refresh(q)

                for opt in options:
                    session.add(Option(question_id=q.id, option_text=opt))

        session.commit()

    with get_session() as session:
        for cert, qs in QUESTIONS.items():
            for qtext, options, correct in qs:
                q = Question(
                    certificate_code=cert,
                    question_text=qtext,
                    correct_option=correct,
                )
                session.add(q)
                session.commit()
                session.refresh(q)

                for opt in options:
                    session.add(Option(question_id=q.id, option_text=opt))

        session.commit()


if __name__ == "__main__":
    load()
    print("Questions loaded successfully.")
