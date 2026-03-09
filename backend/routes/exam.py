"""
VaaniPariksha - Exam Routes
Start exam, voice commands, save answers, submit, status.
"""
import os
import logging
import secrets
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app

from backend.database.db import db
from backend.models.models import Exam, Question, Session, Response
from backend.services.session_manager import SessionState, AutoSaver, save_responses_to_db
from backend.services.voice_engine.command_processor import CommandProcessor
from backend.services.voice_engine.llm_classifier import LLMClassifier
from backend.services.voice_engine.stt_engine import get_stt_engine
from backend.services.answer_generator.pdf_generator import generate_answer_pdf

exam_bp = Blueprint("exam", __name__)
logger = logging.getLogger(__name__)

# In-memory store of active sessions {session_token: SessionState}
_active_sessions: dict = {}
# Auto-savers {session_token: AutoSaver}
_auto_savers: dict = {}


# ----------------------------------------------------------------------- #
# Helper: get or 404
# ----------------------------------------------------------------------- #
def _get_session_state(token: str) -> SessionState:
    state = _active_sessions.get(token)
    if state:
        return state
        
    # Attempt crash recovery from DB
    from backend.services.session_manager.auto_save import recover_session
    from backend.models.models import Session
    
    db_session = Session.query.filter_by(session_token=token).first()
    if not db_session or not db_session.session_data:
        return None
        
    exam_id = db_session.exam_id
    questions = [q.to_dict() for q in Question.query.filter_by(exam_id=exam_id).order_by(Question.id).all()]
    
    recovered_state = recover_session(token, questions)
    if recovered_state:
        _active_sessions[token] = recovered_state
        
        # Restart auto-saver
        saver = AutoSaver(
            session_state=recovered_state, 
            session_db_id=db_session.id, 
            interval=30, 
            app=current_app._get_current_object()
        )
        saver.start()
        _auto_savers[token] = saver
        
        logger.info(f"Dynamically recovered session {token} into memory.")
        return recovered_state
        
    return None


# ----------------------------------------------------------------------- #
# POST /start-exam
# ----------------------------------------------------------------------- #
@exam_bp.route("/start-exam", methods=["POST"])
def start_exam():
    """
    Body JSON: {exam_id, student_name?, student_id?}
    Creates a Session record and initializes in-memory SessionState.
    Returns: {session_token, exam_id, total_questions, first_question}
    """
    data = request.get_json(force=True) or {}
    exam_id = data.get("exam_id")
    if not exam_id:
        return jsonify({"error": "exam_id required"}), 400

    exam = Exam.query.get(exam_id)
    if not exam:
        return jsonify({"error": "Exam not found"}), 404

    questions = (
        Question.query.filter_by(exam_id=exam_id)
        .order_by(Question.id)
        .all()
    )
    if not questions:
        return jsonify({"error": "No questions found for this exam"}), 404

    # Create DB session record
    token = secrets.token_urlsafe(32)
    duration_secs = exam.duration_minutes * 60
    db_session = Session(
        session_token=token,
        exam_id=exam_id,
        student_name=data.get("student_name", "Anonymous"),
        student_id=data.get("student_id", ""),
        status="active",
        time_remaining_seconds=duration_secs,
    )
    db.session.add(db_session)
    db.session.commit()

    # Build in-memory SessionState
    q_dicts = [q.to_dict() for q in questions]
    state = SessionState(
        session_token=token,
        exam_id=exam_id,
        questions=q_dicts,
        duration_seconds=duration_secs,
        student_name=data.get("student_name", "Anonymous"),
        student_id=data.get("student_id", ""),
    )
    _active_sessions[token] = state

    # Start auto-saver
    saver = AutoSaver(state, db_session.id, interval=30, app=current_app._get_current_object())
    saver.start()
    _auto_savers[token] = saver

    first_q = state.current_question()
    return jsonify({
        "success": True,
        "session_token": token,
        "exam_id": exam_id,
        "exam_title": exam.title,
        "total_questions": len(q_dicts),
        "duration_minutes": exam.duration_minutes,
        "first_question": first_q,
    }), 201


# ----------------------------------------------------------------------- #
# POST /voice-command (JSON variant)
# ----------------------------------------------------------------------- #
@exam_bp.route("/voice-command", methods=["POST"])
def voice_command():
    """
    Body JSON: {session_token, transcript, confidence}
    """
    data = request.get_json(force=True) or {}
    token = data.get("session_token")
    transcript = data.get("transcript", "").strip()
    confidence = float(data.get("confidence", 1.0))

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    processor = CommandProcessor(state)
    result = processor.process(transcript, confidence)

    # Standardized response metadata
    result["heard"] = transcript
    result["confidence"] = round(confidence, 3)
    result["alert"] = state.check_time_alerts()
    result["progress"] = state.get_progress()

    return jsonify(result), 200


# ----------------------------------------------------------------------- #
# POST /voice-command-audio
# ----------------------------------------------------------------------- #
@exam_bp.route("/voice-command-audio", methods=["POST"])
def voice_command_audio():
    """
    Form Data: session_token (str), audio (Blob/File - WAV format)
    Processes raw PCM audio via Vosk, then routes to same intent logic.
    """
    token = request.form.get("session_token")
    audio_file = request.files.get("audio")

    if not token or not audio_file:
        return jsonify({"error": "Missing token or audio"}), 400

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    if state.submitted:
        return jsonify({"error": "Exam already submitted"}), 400

    try:
        wav_data = audio_file.read()
        # Minimal WAV checking: header is 44 bytes
        if len(wav_data) < 44:
            return jsonify({"error": "Invalid audio data"}), 400
            
        # Get STT engine and transcribe
        stt = get_stt_engine()
        transcript, confidence = stt.listen_from_audio_data(wav_data)
        
        if not transcript:
            return jsonify({
                "action": "none",
                "heard": "",
                "confidence": 0,
                "progress": state.get_progress()
            }), 200

        # Run CommandProcessor (New LLM-First logic)
        processor = CommandProcessor(state)
        result = processor.process(transcript, confidence)

        # Standardized response metadata for frontend
        result["heard"] = transcript
        result["confidence"] = round(confidence, 3)
        result["alert"] = state.check_time_alerts()
        result["progress"] = state.get_progress()

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Voice processing failed: {e}")
        return jsonify({"error": "STT processing failed"}), 500


# ----------------------------------------------------------------------- #
# POST /confirm-answer
# ----------------------------------------------------------------------- #
@exam_bp.route("/confirm-answer", methods=["POST"])
def confirm_answer():
    """
    Body JSON: {session_token, action: 'confirm'|'repeat'}
    Confirms or discards the pending answer.
    For descriptive/fill_blank: saves in-place and asks for edits.
    For mcq/true_false: saves and advances to next question.
    """
    data = request.get_json(force=True) or {}
    token = data.get("session_token")
    action = data.get("action", "confirm")

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    if action != "confirm":
        state.discard_pending()
        return jsonify({
            "success": True,
            "action": "change_answer",
            "message": "No problem. Please tell me your answer again.",
        })

    # Determine question type
    q = state.current_question()
    q_type = (q.get("question_type") or "descriptive").lower() if q else "descriptive"
    is_open_ended = q_type in ("descriptive", "fill_blank", "short_answer", "long_answer")

    # Save the pending answer (without advancing for QA types)
    state.confirm_pending()
    saved_answer = state.get_answer(q["id"]) if q else ""
    progress = state.get_progress()

    if is_open_ended:
        # For QA: save in-place, keep on same question, ask for edits
        return jsonify({
            "success": True,
            "action": "answer_saved",
            "answer": saved_answer,
            "message": (
                f"Answer saved. "
                f"Is there anything you'd like to add, change, or remove? "
                f"Say 'no changes' or 'next' when you're done."
            ),
            "progress": progress,
        })
    else:
        # For MCQ / True-False: save and advance
        moved = state.move_next()
        if moved:
            next_q = state.current_question()
            q_text = next_q.get("question_text", "") if next_q else ""
            q_num  = next_q.get("question_number", "") if next_q else ""
            opts   = ""
            if next_q and next_q.get("question_type") == "mcq" and next_q.get("options"):
                opts = " The options are: " + ". ".join(
                    [f"Option {k}: {v}" for k, v in next_q["options"].items()]
                ) + "."
            return jsonify({
                "success": True,
                "action": "navigate",
                "question": next_q,
                "message": f"Answer confirmed. Moving to question {q_num}. {q_text}{opts}",
                "progress": state.get_progress(),
            })
        else:
            return jsonify({
                "success": True,
                "action": "confirm",
                "message": "Answer confirmed. This was the last question. Say 'submit' when you're ready to submit.",
                "progress": progress,
            })


# ----------------------------------------------------------------------- #
# POST /save-answer
# ----------------------------------------------------------------------- #
@exam_bp.route("/save-answer", methods=["POST"])
def save_answer():
    """
    Body JSON: {session_token, question_id, answer_text, confidence?}
    Directly save/overwrite an answer (keyboard fallback).
    """
    data = request.get_json(force=True) or {}
    token = data.get("session_token")
    question_id = data.get("question_id")
    answer_text = data.get("answer_text", "")
    confidence = float(data.get("confidence", 1.0))

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    if not question_id:
        return jsonify({"error": "question_id required"}), 400

    state.save_answer(int(question_id), answer_text, confidence)
    return jsonify({
        "success": True,
        "question_id": question_id,
        "progress": state.get_progress(),
    })


# ----------------------------------------------------------------------- #
# POST /navigate  (direct, LLM-free navigation for GUI buttons)
# ----------------------------------------------------------------------- #
@exam_bp.route("/navigate", methods=["POST"])
def navigate():
    """
    Body JSON: {session_token, action: 'next'|'previous'|'goto'|'skip', target?: int}
    Direct navigation without LLM. Used by GUI buttons.
    """
    data   = request.get_json(force=True) or {}
    token  = data.get("session_token")
    action = data.get("action", "next")
    target = data.get("target")  # for 'goto'

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    def _build_message(q):
        """Build spoken question text, including existing answer if already answered."""
        import re as _re
        if not q:
            return ""
        q_id   = q.get("id")
        q_num  = q.get("question_number", "")
        q_text = _re.sub(r'_{2,}', 'blank', q.get("question_text", ""))
        q_type = (q.get("question_type") or "").lower()
        saved  = state.get_answer(q_id) if q_id else ""
        status = state.statuses.get(q_id, "unanswered")

        msg = f"Question {q_num}. {q_text}"
        if q_type == "mcq" and q.get("options"):
            msg += " The options are: "
            for k, v in q["options"].items():
                msg += f"Option {k}: {v}. "
        elif q_type == "true_false":
            msg = f"True or False. {q_text}"

        if saved and status == "answered":
            msg = (f"You have already answered this question. "
                   f"{msg} "
                   f"Your saved answer is: {saved}. "
                   f"Would you like to change it? Say yes to re-answer, or no to keep it.")
        return msg


    if action == "next":
        moved = state.move_next()
        q = state.current_question()
        if moved:
            return jsonify({"action": "navigate", "direction": "next",
                            "question": q, "answer": state.get_answer(q["id"]) if q else None,
                            "message": _build_message(q),
                            "progress": state.get_progress()})
        return jsonify({"action": "end", "message": "This is the last question. Say 'submit' to finish.",
                        "question": q, "progress": state.get_progress()})

    elif action == "previous":
        moved = state.move_previous()
        q = state.current_question()
        if moved:
            return jsonify({"action": "navigate", "direction": "previous",
                            "question": q, "answer": state.get_answer(q["id"]) if q else None,
                            "message": _build_message(q),
                            "progress": state.get_progress()})
        return jsonify({"action": "end", "message": "This is already the first question.",
                        "question": q, "progress": state.get_progress()})

    elif action == "goto" and target is not None:
        moved = state.go_to_question(str(target))
        q = state.current_question()
        if moved:
            return jsonify({"action": "navigate", "direction": "goto",
                            "question": q, "answer": state.get_answer(q["id"]) if q else None,
                            "message": _build_message(q),
                            "progress": state.get_progress()})
        return jsonify({"action": "end", "message": f"Question {target} not found.",
                        "question": q, "progress": state.get_progress()})

    elif action == "skip":
        q_current = state.current_question()
        if q_current:
            state.statuses[q_current["id"]] = "skipped"
        state.move_next()
        q = state.current_question()
        return jsonify({"action": "navigate", "direction": "skip",
                        "question": q, "answer": state.get_answer(q["id"]) if q else None,
                        "message": f"Question skipped. {_build_message(q)}",
                        "progress": state.get_progress()})

    return jsonify({"error": f"Unknown action: {action}"}), 400


# ----------------------------------------------------------------------- #
# POST /transcribe
# ----------------------------------------------------------------------- #
import math
import struct

@exam_bp.route("/transcribe", methods=["POST"])
def transcribe_audio():
    """Simple transcription without session context (used for onboarding)."""
    audio_file = request.files.get("audio")
    if not audio_file:
        logger.error("No audio file uploaded to /transcribe")
        return jsonify({"transcript": ""}), 400
    try:
        wav_data = audio_file.read()
        if len(wav_data) < 44:
            logger.error(f"Audio file too small: {len(wav_data)} bytes")
            return jsonify({"transcript": ""}), 400
        # Get STT engine
        from backend.services.voice_engine.stt_engine import get_stt_engine
        
        stt = get_stt_engine()
        transcript, conf = stt.listen_from_audio_data(wav_data)
        
        return jsonify({"transcript": transcript, "confidence": conf})
    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        return jsonify({"transcript": ""}), 500


# ----------------------------------------------------------------------- #
# POST /clean-id
# ----------------------------------------------------------------------- #
@exam_bp.route("/clean-id", methods=["POST"])
def clean_id():
    """Uses LLM to clean alphanumeric student IDs."""
    from backend.services.voice_engine.id_cleaner import IDCleaner
    data = request.get_json(force=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"id": ""})
    
    cleaner = IDCleaner()
    cleaned = cleaner.clean_id(text)
    return jsonify({"id": cleaned})
@exam_bp.route("/status/<session_token>", methods=["GET"])
def exam_status(session_token):
    """Get current exam progress without any voice processing."""
    state = _get_session_state(session_token)
    if not state:
        return jsonify({"error": "Session not found"}), 404
    progress = state.get_progress()
    progress["status_text"] = state.get_status_text()
    progress["current_question"] = state.current_question()
    return jsonify(progress)


# ----------------------------------------------------------------------- #
# POST /submit-exam
# ----------------------------------------------------------------------- #
@exam_bp.route("/submit-exam", methods=["POST"])
def submit_exam():
    """
    Body JSON: {session_token}
    Finalizes the exam: saves all responses, generates answer PDF.
    """
    data = request.get_json(force=True) or {}
    token = data.get("session_token")

    state = _get_session_state(token)
    if not state:
        return jsonify({"error": "Session not found"}), 404

    if state.submitted:
        return jsonify({"error": "Exam already submitted"}), 400

    # Mark submitted
    state.submitted = True

    # Stop auto-saver
    saver = _auto_savers.pop(token, None)
    if saver:
        saver.stop()

    # Save all responses to DB
    db_session = Session.query.filter_by(session_token=token).first()
    if not db_session:
        return jsonify({"error": "DB session not found"}), 500

    try:
        save_responses_to_db(db_session.id, state)
    except Exception as e:
        logger.error(f"Response save failed: {e}")

    # Generate answer PDF
    exam = Exam.query.get(state.exam_id)
    output_dir = current_app.config.get("GENERATED_PDF_FOLDER", "./generated_pdfs")
    output_path = os.path.join(output_dir, f"answers_{token[:16]}.pdf")

    try:
        generate_answer_pdf(
            output_path=output_path,
            exam_title=exam.title if exam else "Exam",
            questions=state.questions,
            answers=state.answers,
            statuses=state.statuses,
            student_id=state.student_id,
            exam_duration_minutes=exam.duration_minutes if exam else 60,
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500

    # Update DB session
    db_session.status = "submitted"
    db_session.generated_pdf_path = output_path
    db_session.end_time = datetime.now(timezone.utc)
    elapsed = state.elapsed_seconds()
    db_session.duration_seconds = int(elapsed)
    db.session.commit()

    # Cleanup audio
    try:
        from backend.services.security.encryption import delete_temp_audio
        delete_temp_audio()
    except Exception:
        pass

    # Remove from active sessions
    _active_sessions.pop(token, None)

    return jsonify({
        "success": True,
        "session_token": token,
        "pdf_ready": True,
        "pdf_download_url": f"/download-pdf/{token}",
        "progress": state.get_progress(),
    })


# ----------------------------------------------------------------------- #
# GET /get-question/<session_token>
# ----------------------------------------------------------------------- #
@exam_bp.route("/get-question/<session_token>", methods=["GET"])
def get_question(session_token):
    """Get current question details for a session."""
    state = _get_session_state(session_token)
    if not state:
        return jsonify({"error": "Session not found"}), 404
    q = state.current_question()
    return jsonify({
        "question": q,
        "answer": state.get_answer(q["id"]) if q else None,
        "status": state.statuses.get(q["id"], "unanswered") if q else None,
        "progress": state.get_progress(),
    })
