"""
VaaniPariksha - Download & Admin Routes
"""
import os
import logging
from flask import Blueprint, send_file, jsonify, current_app, abort, request
from backend.models.models import Session, Exam, Question, Response
from backend.database.db import db
from sqlalchemy import func

download_bp = Blueprint("download", __name__)
admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------- #
# GET /download-pdf/<session_token>
# ----------------------------------------------------------------------- #
@download_bp.route("/download-pdf/<session_token>", methods=["GET"])
def download_pdf(session_token):
    """Download the generated answer PDF for a submitted session."""
    db_session = Session.query.filter_by(session_token=session_token).first()
    if not db_session:
        return jsonify({"error": "Session not found"}), 404
    if db_session.status != "submitted":
        return jsonify({"error": "Exam not yet submitted"}), 400
    if not db_session.generated_pdf_path:
        return jsonify({"error": "PDF not generated yet"}), 404

    pdf_path = db_session.generated_pdf_path

    # Try AWS S3 if path looks like S3 key
    if not os.path.isabs(pdf_path) and not os.path.exists(pdf_path):
        try:
            from backend.utils.aws_s3 import get_presigned_url
            url = get_presigned_url(pdf_path)
            if url:
                from flask import redirect
                return redirect(url)
        except Exception as e:
            logger.error(f"S3 redirect failed: {e}")

    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF file not found on server"}), 404

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"vaanipariksha_answers_{session_token[:8]}.pdf",
    )


# ----------------------------------------------------------------------- #
# GET /admin/dashboard
# ----------------------------------------------------------------------- #
@admin_bp.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    """
    Hackathon admin panel data.
    Returns summary of all exams and active sessions.
    """
    # All exams
    exams = Exam.query.order_by(Exam.created_at.desc()).limit(20).all()

    # Active sessions
    active = Session.query.filter(Session.status == "active").all()
    submitted = Session.query.filter(Session.status == "submitted").order_by(Session.end_time.desc()).limit(50).all()
    crashed = Session.query.filter(Session.status == "crashed").count()

    exam_list = []
    for exam in exams:
        sessions_count = Session.query.filter_by(exam_id=exam.id).count()
        submitted_count = Session.query.filter_by(
            exam_id=exam.id, status="submitted"
        ).count()
        exam_list.append({
            **exam.to_dict(),
            "sessions_total": sessions_count,
            "sessions_submitted": submitted_count,
        })

    active_list = []
    for s in active:
        active_list.append({
            "session_token": s.session_token[:12] + "...",
            "exam_id": s.exam_id,
            "exam_code": s.exam.exam_code if s.exam else str(s.exam_id),
            "student_name": s.student_name,
            "student_id": s.student_id or "—",
            "status": s.status,
            "time_remaining_seconds": s.time_remaining_seconds,
            "last_saved_at": s.last_saved_at.isoformat() if s.last_saved_at else None,
            "current_question": s.current_question_num,
        })

    submitted_list = []
    for s in submitted:
        submitted_list.append({
            "session_token": s.session_token,
            "short_token": s.session_token[:12] + "...",
            "exam_id": s.exam_id,
            "exam_code": s.exam.exam_code if s.exam else str(s.exam_id),
            "student_id": s.student_id or "—",
            "end_time": s.end_time.isoformat() if s.end_time else s.updated_at.isoformat(),
            "pdf_ready": bool(s.generated_pdf_path)
        })

    return jsonify({
        "summary": {
            "total_exams": len(exams),
            "active_sessions": len(active_list),
            "submitted_sessions": Session.query.filter(Session.status == "submitted").count(),
            "crashed_sessions": crashed,
        },
        "exams": exam_list,
        "active_sessions": active_list,
        "submitted_sessions": submitted_list,
    })


@admin_bp.route("/admin/exams", methods=["GET"])
def list_exams():
    """List all exams with question counts."""
    exams = Exam.query.order_by(Exam.created_at.desc()).all()
    return jsonify({"exams": [e.to_dict() for e in exams]})


@admin_bp.route("/admin/exam/<int:exam_id>", methods=["DELETE"])
def delete_exam(exam_id):
    """Delete an exam and all its associated questions and sessions."""
    exam = Exam.query.get(exam_id)
    if not exam:
        return jsonify({"error": "Exam not found"}), 404
    
    try:
        # Cascade delete is handled by SQLAlchemy backref
        db.session.delete(exam)
        db.session.commit()
        return jsonify({"success": True, "message": "Exam deleted successfully"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete exam: {e}")
        return jsonify({"error": f"Failed to delete exam: {str(e)}"}), 500


@admin_bp.route("/admin/exam/<int:exam_id>", methods=["PATCH"])
def update_exam(exam_id):
    """Update exam title or duration."""
    exam = Exam.query.get(exam_id)
    if not exam:
        return jsonify({"error": "Exam not found"}), 404
    
    data = request.get_json() or {}
    if "title" in data:
        exam.title = data["title"]
    if "duration_minutes" in data:
        exam.duration_minutes = int(data["duration_minutes"])
        
    try:
        db.session.commit()
        return jsonify({"success": True, "exam": exam.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update exam: {e}")
        return jsonify({"error": f"Database error"}), 500
