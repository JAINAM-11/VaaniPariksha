"""
VaaniPariksha - Session State
In-memory session state for an active exam session.
Tracks current question, answers, timer, and progress.
"""
import time
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class SessionState:
    """
    Active exam session state (in-memory).
    All exam navigation and answer tracking goes through this class.
    """

    def __init__(
        self,
        session_token: str,
        exam_id: int,
        questions: List[Dict],
        duration_seconds: int,
        student_name: str = "Anonymous",
        student_id: str = "",
    ):
        self.session_token = session_token
        self.exam_id = exam_id
        self.questions = questions          # list of question dicts (ordered)
        self.total_questions = len(questions)
        self.duration_seconds = duration_seconds
        self.student_name = student_name
        self.student_id = student_id        # Alphanumeric ID (e.g., 24A5)
        self.previous_response_text: str = "" # Last message spoken by system

        # Navigation
        self.current_q_index: int = 0       # 0-based index into self.questions

        # Answers: {question_id: answer_text}
        self.answers: Dict[int, str] = {}
        # Statuses: {question_id: 'answered'|'skipped'|'unanswered'}
        self.statuses: Dict[int, str] = {}
        # Confidence scores: {question_id: float}
        self.confidence_scores: Dict[int, float] = {}

        # Timer
        self.start_time: float = time.time()
        self.paused_at: Optional[float] = None
        self.total_paused_seconds: float = 0.0

        # Flags
        self.submitted: bool = False
        self.crashed: bool = False
        self._alerts_fired: set = set()  # tracks fired alerts: {75, 90, 95}

        # Pending confirmation (for low-confidence answers)
        self.pending_answer: Optional[str] = None
        self.pending_confidence: float = 0.0

        # QA conversation state machine (explicit, not inferred from text)
        # Values: None | 'awaiting_modify_yn' | 'awaiting_modification'
        #        | 'awaiting_save_yn' | 'awaiting_modify_or_remove'
        self.qa_conv_state: Optional[str] = None

        # Init all statuses as 'unanswered'
        for q in questions:
            self.statuses[q["id"]] = "unanswered"

    # ----------------------------------------------------------------------- #
    # Navigation
    # ----------------------------------------------------------------------- #
    def current_question(self) -> Optional[Dict]:
        if 0 <= self.current_q_index < self.total_questions:
            return self.questions[self.current_q_index]
        return None

    def move_next(self) -> bool:
        if self.current_q_index < self.total_questions - 1:
            self.current_q_index += 1
            return True
        return False

    def move_previous(self) -> bool:
        if self.current_q_index > 0:
            self.current_q_index -= 1
            return True
        return False

    def go_to_question(self, target: str) -> bool:
        """Navigate to question by question_number string."""
        for i, q in enumerate(self.questions):
            if str(q.get("question_number", "")) == str(target):
                self.current_q_index = i
                return True
        return False

    # ----------------------------------------------------------------------- #
    # Answer management
    # ----------------------------------------------------------------------- #
    def save_answer(self, question_id: int, answer_text: str, confidence: float = 1.0):
        """Store/overwrite confirmed answer for a question."""
        self.answers[question_id] = answer_text
        self.statuses[question_id] = "answered"
        self.confidence_scores[question_id] = confidence
        logger.debug(f"Answer saved for q_id={question_id}: '{answer_text[:50]}'")

    def mark_skipped(self, q_index: int):
        if 0 <= q_index < self.total_questions:
            q_id = self.questions[q_index]["id"]
            self.statuses[q_id] = "skipped"
            if q_id in self.answers:
                del self.answers[q_id]

    def get_answer(self, question_id: int) -> str:
        return self.answers.get(question_id, "")

    def set_pending(self, answer: str, confidence: float):
        """Store a pending (unconfirmed) answer."""
        self.pending_answer = answer
        self.pending_confidence = confidence

    def confirm_pending(self):
        """Confirm the pending answer for current question."""
        q = self.current_question()
        if q and self.pending_answer is not None:
            self.save_answer(q["id"], str(self.pending_answer), self.pending_confidence)
            self.pending_answer = None
            self.pending_confidence = 0.0

    def confirm_and_advance(self) -> bool:
        """Confirms pending answer and moves to next question. Returns True if moved."""
        self.confirm_pending()
        return self.move_next()

    def discard_pending(self):
        self.pending_answer = None
        self.pending_confidence = 0.0

    def apply_answer_edit(self, q_id: int, action: str, text: str, confidence: float = 1.0):
        """
        Apply a sentence-level edit to an existing answer and stage it as pending.
        action: 'new' | 'append' | 'replace_sentence' | 'remove_sentence'
        Returns the previewed (pending) full answer string.
        """
        existing = self.get_answer(q_id) or ""

        if action == "append":
            preview = f"{existing} {text}".strip() if existing else text
        elif action == "replace_sentence":
            # text is the complete replacement answer supplied by the LLM
            preview = text
        elif action == "remove_sentence":
            sentences = [s.strip() for s in existing.split(".") if s.strip()]
            if sentences:
                sentences.pop()
            preview = ". ".join(sentences) + ("." if sentences else "")
        else:  # 'new'
            preview = text

        self.set_pending(preview, confidence)
        return preview

    # ----------------------------------------------------------------------- #
    # Progress
    # ----------------------------------------------------------------------- #
    def get_progress(self) -> Dict[str, Any]:
        answered = sum(1 for s in self.statuses.values() if s == "answered")
        skipped = sum(1 for s in self.statuses.values() if s == "skipped")
        unanswered = self.total_questions - answered - skipped
        remaining = max(0.0, self.time_remaining())
        return {
            "total": self.total_questions,
            "answered": answered,
            "skipped": skipped,
            "unanswered": unanswered,
            "time_remaining_seconds": int(remaining),
            "current_index": self.current_q_index,
            "current_q_number": (self.current_question() or {}).get("question_number", ""),
            "question_statuses": {str(q["question_number"]): self.statuses.get(q["id"], "unanswered") for q in self.questions},
        }

    def get_progress_summary(self) -> str:
        """Concise string for LLM context."""
        p = self.get_progress()
        return f"{p['answered']}/{p['total']} answered, {p['skipped']} skipped."

    def get_status_text(self) -> str:
        p = self.get_progress()
        mins = p["time_remaining_seconds"] // 60
        secs = p["time_remaining_seconds"] % 60
        return (
            f"You have answered {p['answered']} out of {p['total']} questions. "
            f"{p['skipped']} are skipped. "
            f"{mins} minutes and {secs} seconds remaining."
        )

    # 🧠 MULTI-SENTENCE ANSWER MANAGEMENT
    def append_sentence(self, q_id: int, sentence: str):
        existing = self.get_answer(q_id)
        new_ans = f"{existing} {sentence}".strip()
        self.save_answer(q_id, new_ans)

    def replace_sentence(self, q_id: int, old_phrase: str, new_phrase: str):
        existing = self.get_answer(q_id)
        new_ans = existing.replace(old_phrase, new_phrase)
        self.save_answer(q_id, new_ans)

    def remove_last_sentence(self, q_id: int):
        existing = self.get_answer(q_id)
        sentences = existing.split(". ")
        if sentences:
            sentences.pop()
            new_ans = ". ".join(sentences)
            self.save_answer(q_id, new_ans)

    def check_time_alerts(self) -> Optional[str]:
        """Check if we should fire a time alert. Returns alert text or None."""
        if self.duration_seconds <= 0:
            return None
        elapsed = self.elapsed_seconds()
        pct = (elapsed / self.duration_seconds) * 100
        for threshold in [75, 90, 95]:
            if pct >= threshold and threshold not in self._alerts_fired:
                self._alerts_fired.add(threshold)
                remaining_mins = max(0, (self.duration_seconds - elapsed)) // 60
                return (
                    f"Alert: {100 - threshold} percent of exam time remaining. "
                    f"Approximately {int(remaining_mins)} minutes left."
                )
        return None

    # ----------------------------------------------------------------------- #
    # Timer
    # ----------------------------------------------------------------------- #
    def elapsed_seconds(self) -> float:
        if self.paused_at:
            return self.paused_at - self.start_time - self.total_paused_seconds
        return time.time() - self.start_time - self.total_paused_seconds

    def time_remaining(self) -> float:
        return max(0.0, self.duration_seconds - self.elapsed_seconds())

    def pause_timer(self):
        if not self.paused_at:
            self.paused_at = time.time()

    def resume_timer(self):
        if self.paused_at:
            self.total_paused_seconds += time.time() - self.paused_at
            self.paused_at = None

    # ----------------------------------------------------------------------- #
    # Serialization (for crash recovery)
    # ----------------------------------------------------------------------- #
    def to_snapshot(self) -> Dict:
        """Serialize state to a JSON-safe dict."""
        return {
            "session_token": self.session_token,
            "exam_id": self.exam_id,
            "student_name": self.student_name,
            "current_q_index": self.current_q_index,
            "answers": {str(k): v for k, v in self.answers.items()},
            "statuses": {str(k): v for k, v in self.statuses.items()},
            "confidence_scores": {str(k): v for k, v in self.confidence_scores.items()},
            "start_time": self.start_time,
            "total_paused_seconds": self.total_paused_seconds,
            "duration_seconds": self.duration_seconds,
            "student_id": self.student_id,
            "previous_response_text": self.previous_response_text,
            "alerts_fired": list(self._alerts_fired),
            "submitted": self.submitted,
        }

    def restore_snapshot(self, snapshot: Dict):
        """Restore in-memory state from a snapshot dict."""
        self.current_q_index = snapshot.get("current_q_index", 0)
        self.answers = {int(k): v for k, v in snapshot.get("answers", {}).items()}
        self.statuses = {int(k): v for k, v in snapshot.get("statuses", {}).items()}
        self.confidence_scores = {int(k): v for k, v in snapshot.get("confidence_scores", {}).items()}
        self.start_time = snapshot.get("start_time", time.time())
        self.total_paused_seconds = snapshot.get("total_paused_seconds", 0.0)
        self.duration_seconds = snapshot.get("duration_seconds", self.duration_seconds)
        self.student_id = snapshot.get("student_id", "")
        self.previous_response_text = snapshot.get("previous_response_text", "")
        self._alerts_fired = set(snapshot.get("alerts_fired", []))
        self.submitted = snapshot.get("submitted", False)
        logger.info(f"Session {self.session_token} restored from snapshot.")
