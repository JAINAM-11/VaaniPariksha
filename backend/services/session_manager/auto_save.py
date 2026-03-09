"""
VaaniPariksha - Auto-Save & Crash Recovery
Background thread saves session state to DB every 30 seconds.
"""
import time
import threading
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AutoSaver:
    """
    Background daemon thread that saves session state to DB periodically.
    """

    def __init__(self, session_state, session_db_id: int, interval: int = 30, app=None):
        self.state = session_state
        self.session_db_id = session_db_id
        self.interval = interval
        self.app = app          # Flask app (for app context)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="AutoSaver")
        self._thread.start()
        logger.info(f"AutoSaver started (interval={self.interval}s) for session {self.state.session_token}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AutoSaver stopped.")

    def _run(self):
        while not self._stop_event.wait(timeout=self.interval):
            self._save_snapshot()

    def _save_snapshot(self):
        try:
            if self.app:
                with self.app.app_context():
                    self._write_to_db()
            else:
                self._write_to_db()
        except Exception as e:
            logger.error(f"AutoSave failed: {e}")

    def _write_to_db(self):
        from backend.database.db import db
        from backend.models.models import Session

        session = Session.query.get(self.session_db_id)
        if not session:
            return
        snapshot = self.state.to_snapshot()
        session.session_data = snapshot
        session.last_saved_at = datetime.now(timezone.utc)
        session.current_question_num = str(
            self.state.current_question().get("question_number", "1")
            if self.state.current_question() else "1"
        )
        progress = self.state.get_progress()
        session.time_remaining_seconds = progress["time_remaining_seconds"]
        db.session.commit()
        logger.debug(f"AutoSaved session {self.state.session_token}")


# --------------------------------------------------------------------------- #
# Crash recovery
# --------------------------------------------------------------------------- #

def save_responses_to_db(session_db_id: int, state, app=None):
    """Persist all current answers from SessionState to the responses table."""
    def _write():
        from backend.database.db import db
        from backend.models.models import Response
        for q in state.questions:
            q_id = q["id"]
            answer = state.answers.get(q_id)
            status = state.statuses.get(q_id, "unanswered")
            confidence = state.confidence_scores.get(q_id)

            existing = Response.query.filter_by(
                session_id=session_db_id, question_id=q_id
            ).first()
            if existing:
                existing.answer_text = answer
                existing.status = status
                existing.confidence_score = confidence
                existing.confirmed = True
            else:
                db.session.add(Response(
                    session_id=session_db_id,
                    question_id=q_id,
                    answer_text=answer,
                    status=status,
                    confidence_score=confidence,
                    confirmed=True,
                ))
        db.session.commit()
        logger.info(f"Responses saved for session_id={session_db_id}")

    if app:
        with app.app_context():
            _write()
    else:
        _write()


def recover_session(session_token: str, questions: list, app=None):
    """
    Recover a SessionState from the DB snapshot after crash.
    Returns a new SessionState with state restored, or None.
    """
    def _load():
        from backend.models.models import Session
        sess = Session.query.filter_by(session_token=session_token).first()
        if not sess or not sess.session_data:
            return None, None
        return sess, sess.session_data

    if app:
        with app.app_context():
            sess, snapshot = _load()
    else:
        from backend.models.models import Session
        sess = Session.query.filter_by(session_token=session_token).first()
        snapshot = sess.session_data if sess else None

    if not snapshot:
        return None

    from backend.services.session_manager.session_state import SessionState
    state = SessionState(
        session_token=session_token,
        exam_id=snapshot.get("exam_id", 0),
        questions=questions,
        duration_seconds=snapshot.get("duration_seconds", 3600),
        student_name=snapshot.get("student_name", "Anonymous"),
    )
    state.restore_snapshot(snapshot)
    logger.info(f"Recovered session {session_token}")
    return state
