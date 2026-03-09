"""
VaaniPariksha - Question DB Writer
Persists parsed questions to the database.
"""
import logging
from typing import List, Dict
from backend.database.db import db
from backend.models.models import Exam, Question

logger = logging.getLogger(__name__)


def save_questions_to_db(exam_id: int, questions: List[Dict]) -> int:
    """
    Persist a list of parsed question dicts to the DB using bulk insertion.
    Returns count of questions saved.
    """
    count = 0
    try:
        mappings = []
        for q in questions:
            count += 1
            mappings.append({
                "exam_id": exam_id,
                "question_number": q.get("question_number", str(count)),
                "parent_number": q.get("parent_number"),
                "question_type": q.get("question_type", "short_answer"),
                "question_text": q.get("question_text", ""),
                "options": q.get("options"),
                "marks": q.get("marks", 1.0),
                "page_number": q.get("page_number", 1),
                "position_data": q.get("position_data", {}),
            })
        
        # Performance: Use bulk insert mappings
        if mappings:
            db.session.bulk_insert_mappings(Question, mappings)

        # Update exam's total question count and status
        exam = Exam.query.get(exam_id)
        if exam:
            exam.total_questions = count
            exam.status = "active"
        
        db.session.commit()
        logger.info(f"Saved {count} questions for exam_id={exam_id} using bulk insert.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to save questions: {e}")
        raise
    return count


def get_questions_for_exam(exam_id: int) -> List[Dict]:
    """Retrieve all questions for an exam as list of dicts."""
    questions = (
        Question.query.filter_by(exam_id=exam_id)
        .order_by(Question.id)
        .all()
    )
    return [q.to_dict() for q in questions]
