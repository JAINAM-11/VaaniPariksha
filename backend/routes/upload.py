"""
VaaniPariksha - Flask Upload Route
Handles PDF upload, validation, parsing, and DB persistence.
"""
import os
import logging
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from backend.services.pdf_processor import (
    validate_pdf, PDFValidationError, PDFParser,
    save_questions_to_db
)
from backend.models.models import Exam
from backend.database.db import db

upload_bp = Blueprint("upload", __name__)
logger = logging.getLogger(__name__)


@upload_bp.route("/upload", methods=["POST"])
def upload_pdf():
    """
    POST /upload
    Body: multipart/form-data with 'pdf' file and optional 'title', 'duration'
    Returns: {exam_id, exam_code, title, total_questions, questions[]}
    """
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF file provided. Use key 'pdf'."}), 400

    file = request.files["pdf"]
    if not file.filename:
        return jsonify({"error": "Empty filename."}), 400

    # --- Save temp file ---
    upload_dir = current_app.config.get("UPLOAD_FOLDER", "./uploads")
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    temp_path = os.path.join(upload_dir, filename)
    file.save(temp_path)

    # --- Validate ---
    try:
        validation = validate_pdf(
            temp_path,
            max_size_bytes=current_app.config.get("MAX_PDF_SIZE_BYTES", 50 * 1024 * 1024)
        )
    except PDFValidationError as e:
        os.remove(temp_path)
        return jsonify({"error": str(e)}), 422

    # --- Parse ---
    try:
        tesseract_cmd = current_app.config.get(
            "TESSERACT_CMD",
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        parser = PDFParser(temp_path, tesseract_cmd=tesseract_cmd)
        questions_data = parser.parse()
        metadata = parser.get_metadata()
    except Exception as e:
        logger.error(f"PDF parsing failed: {e}")
        return jsonify({"error": f"PDF parsing failed: {str(e)}"}), 500

    if not questions_data:
        return jsonify({"error": "No questions detected in the PDF."}), 422

    # --- Create Exam in DB ---
    import time
    start_db = time.time()
    try:
        title = request.form.get("title") or metadata.get("title") or filename.replace(".pdf", "")
        duration = int(request.form.get("duration", 60))
        mode = current_app.config.get("STORAGE_MODE", "local")

        exam = Exam(
            title=title,
            original_filename=filename,
            pdf_path=temp_path,
            storage_mode=mode,
            duration_minutes=duration,
            metadata_={"page_count": validation.get("page_count", 1), **metadata},
        )
        db.session.add(exam)
        db.session.flush()  # get exam.id before commit

        exam.total_questions = len(questions_data)
        count = save_questions_to_db(exam.id, questions_data)
        db.session.commit()
        logger.info(f"DB save took {time.time() - start_db:.2f}s for {count} questions.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"DB save failed: {e}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    # --- Optional S3 upload ---
    if mode == "aws":
        try:
            from backend.utils.aws_s3 import upload_pdf_to_s3
            s3_key = f"exams/{exam.exam_code}/{filename}"
            upload_pdf_to_s3(temp_path, s3_key)
            exam.pdf_path = s3_key
            db.session.commit()
        except Exception as e:
            logger.warning(f"S3 upload skipped: {e}")

    return jsonify({
        "success": True,
        "exam_id": exam.id,
        "exam_code": exam.exam_code,
        "title": exam.title,
        "total_questions": count,
        "page_count": validation.get("page_count", 1),
        "questions": [q for q in questions_data[:5]],  # preview first 5
    }), 201

# ----------------------------------------------------------------------- #
# GET /exams
# ----------------------------------------------------------------------- #
@upload_bp.route("/exams", methods=["GET"])
def list_exams():
    """Returns a list of all uploaded exams."""
    try:
        exams = Exam.query.order_by(Exam.created_at.desc()).all()
        return jsonify({
            "success": True,
            "exams": [
                {
                    "id": ex.id,
                    "title": ex.title,
                    "duration_minutes": ex.duration_minutes,
                    "created_at": ex.created_at.isoformat(),
                    "total_questions": ex.total_questions
                }
                for ex in exams
            ]
        })
    except Exception as e:
        logger.error(f"Failed to fetch exams: {e}")
        return jsonify({"error": "Database error"}), 500
