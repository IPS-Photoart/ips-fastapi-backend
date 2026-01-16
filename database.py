from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session

DATABASE_URL = "sqlite:///./ips_platform.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

# --------------------
# MODELS
# --------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Attempt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    course_level: int
    attempt_number: int
    total_marks: float
    total_marks_obtained: float
    percentage: float
    grade: str
    is_passed: bool
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Answer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: int
    question_id: int
    selected_option_id: Optional[int]
    correct_option: Optional[int]
    marks_awarded: float

class Certificate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    course_level: int
    attempt_id: int
    certificate_code: str
    grade: str
    percentage: float
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    verification_url: Optional[str] = None
    is_paid: bool = Field(default=False)

# --------------------
# HELPERS
# --------------------
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
