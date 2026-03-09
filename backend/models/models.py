"""VaaniPariksha - SQLAlchemy ORM Models"""
import secrets
from datetime import datetime, timezone
from backend.database.db import db


class Exam(db.Model):
    __tablename__ = "exams"

    id = db.Column(db.Integer, primary_key=True)
    exam_code = db.Column(db.String(64), unique=True, nullable=False,
                          default=lambda: secrets.token_hex(6).upper())
    title = db.Column(db.String(255), nullable=False, default="Untitled Exam")
    original_filename = db.Column(db.String(255))
    pdf_path = db.Column(db.Text)
    storage_mode = db.Column(db.String(10), default="local")
    total_questions = db.Column(db.Integer, default=0)
    duration_minutes = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default="pending")
    metadata_ = db.Column("metadata", db.JSON, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    questions = db.relationship("Question", backref="exam", lazy="dynamic", cascade="all, delete-orphan")
    sessions = db.relationship("Session", backref="exam", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "exam_code": self.exam_code,
            "title": self.title,
            "original_filename": self.original_filename,
            "total_questions": self.total_questions,
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    question_number = db.Column(db.String(20), nullable=False)
    parent_number = db.Column(db.String(20))
    question_type = db.Column(db.String(30), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, default=None)  # MCQ options dict
    marks = db.Column(db.Numeric(5, 2), default=1)
    page_number = db.Column(db.Integer, default=1)
    position_data = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    responses = db.relationship("Response", backref="question", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "exam_id": self.exam_id,
            "question_number": self.question_number,
            "parent_number": self.parent_number,
            "question_type": self.question_type,
            "question_text": self.question_text,
            "options": self.options,
            "marks": float(self.marks) if self.marks else 1.0,
            "page_number": self.page_number,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False,
                              default=lambda: secrets.token_urlsafe(32))
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_name = db.Column(db.String(255), default="Anonymous")
    student_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default="active")
    current_question_num = db.Column(db.String(20), default="1")
    start_time = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    end_time = db.Column(db.DateTime(timezone=True))
    duration_seconds = db.Column(db.Integer)
    time_remaining_seconds = db.Column(db.Integer)
    last_saved_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    session_data = db.Column(db.JSON, default=dict)  # crash recovery snapshot
    generated_pdf_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    responses = db.relationship("Response", backref="session", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "session_token": self.session_token,
            "exam_id": self.exam_id,
            "student_name": self.student_name,
            "status": self.status,
            "current_question_num": self.current_question_num,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "time_remaining_seconds": self.time_remaining_seconds,
            "last_saved_at": self.last_saved_at.isoformat() if self.last_saved_at else None,
            "generated_pdf_path": self.generated_pdf_path,
        }


class Response(db.Model):
    __tablename__ = "responses"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_text = db.Column(db.Text)
    answer_encrypted = db.Column(db.LargeBinary)
    status = db.Column(db.String(20), default="unanswered")
    confidence_score = db.Column(db.Numeric(4, 3))
    confirmed = db.Column(db.Boolean, default=False)
    attempt_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint("session_id", "question_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "question_id": self.question_id,
            "answer_text": self.answer_text,
            "status": self.status,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "confirmed": self.confirmed,
            "attempt_count": self.attempt_count,
        }
