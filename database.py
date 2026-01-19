from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, create_engine, Session


# --------------------
# DATABASE
# --------------------
DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, echo=False)


# --------------------
# CORE MODELS
# --------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    email: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CertificateType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    code: str = Field(index=True, unique=True)
    title: str
    abbreviation: str

    duration_minutes: int
    mcq_count: int
    short_answer_count: int

    mcq_mark: int
    pass_percentage: float

    description: str


class Attempt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    certificate_code: str

    total_marks: int
    marks_obtained: int
    percentage: float

    is_passed: bool
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Answer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    attempt_id: int = Field(foreign_key="attempt.id")
    question_id: int = Field(foreign_key="question.id")

    selected_option: Optional[int] = None
    marks_awarded: int = 0

class Certificate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    certificate_code: str = Field(index=True, unique=True)

    certificate_type_code: str
    grade: str
    percentage: float

    is_paid: bool = False
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    verification_url: Optional[str] = None


# --------------------
# QUESTION MODELS (NEW)
# --------------------
class Question(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    certificate_code: str = Field(index=True)
    question_text: str
    correct_option: int  # 1-based index


class Option(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    question_id: int = Field(foreign_key="question.id")
    option_text: str


# --------------------
# HELPERS
# --------------------
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
