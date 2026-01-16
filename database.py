from typing import Optional, List
from datetime import datetime

from sqlmodel import (
    SQLModel,
    Field,
    Session,
    create_engine,
    Column,
)
from sqlalchemy import JSON


# -------------------------------------------------
# DATABASE CONFIG
# -------------------------------------------------
DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


# -------------------------------------------------
# USER
# -------------------------------------------------
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    email: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------
# CERTIFICATE TYPE (EXAM DEFINITION)
# -------------------------------------------------
class CertificateType(SQLModel, table=True):
    __tablename__ = "certificate_types"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identification
    code: str = Field(index=True, unique=True)
    title: str

    # Exam structure
    duration_minutes: int
    mcq_count: int
    short_answer_count: int
    has_ai_evaluation: bool = Field(default=False)

    # Evaluation
    pass_percentage: float

    # Fees
    exam_fee: int
    certificate_fee: int

    # Status
    is_active: bool = Field(default=True)


# -------------------------------------------------
# QUESTIONS
# -------------------------------------------------
class Question(SQLModel, table=True):
    __tablename__ = "questions"

    id: Optional[int] = Field(default=None, primary_key=True)

    certificate_code: str = Field(index=True)

    question: str

    # MCQ specific
    options: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON)
    )
    correct_option: Optional[int] = None

    # Common
    question_type: str   # "MCQ" or "SHORT"
    max_marks: int


# -------------------------------------------------
# EXAM ATTEMPT
# -------------------------------------------------
class Attempt(SQLModel, table=True):
    __tablename__ = "attempts"

    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(index=True)
    certificate_code: str = Field(index=True)

    total_marks: int
    total_marks_obtained: int = 0
    percentage: float = 0.0

    grade: str = "FAIL"
    is_passed: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------
# ANSWERS
# -------------------------------------------------
class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    id: Optional[int] = Field(default=None, primary_key=True)

    attempt_id: int = Field(index=True)
    question_id: int = Field(index=True)

    # For MCQ: option number
    # For SHORT: raw text answer (stored as string)
    selected_option_id: Optional[str] = None

    correct_option: Optional[int] = None
    marks_awarded: int = 0


# -------------------------------------------------
# CERTIFICATE ISSUED
# -------------------------------------------------
class Certificate(SQLModel, table=True):
    __tablename__ = "certificates"

    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(index=True)
    certificate_type: str = Field(index=True)

    certificate_code: str = Field(unique=True, index=True)

    percentage: float
    grade: str

    is_paid: bool = Field(default=False)
    issued_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
