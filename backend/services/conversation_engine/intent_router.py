"""
VaaniPariksha - Intent Router
Maps LLM intents to Exam Engine actions, enforcing strict conversational flows.
"""
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


class IntentRouter:
    def __init__(self, session_state):
        self.state = session_state

    def route(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """Routes the LLM result to the appropriate exam engine action."""
        res_type      = llm_result.get("type", "clarification")
        cmd           = llm_result.get("command", "none")
        answer_text   = llm_result.get("answer_text") or ""
        answer_action = llm_result.get("answer_action", "new")
        spoken_msg    = llm_result.get("spoken_message",
                                        "I didn't quite understand. Could you repeat that?")
        choice_letter = llm_result.get("choice_letter")

        # ── COMMANDS ──────────────────────────────────────────────────────────
        if res_type == "command":
            return self._handle_command(cmd, llm_result)

        # ── ANSWERS & EDITS ───────────────────────────────────────────────────
        if res_type in ("answer", "edit"):
            q      = self.state.current_question()
            q_type = (q.get("question_type") or "descriptive").lower() if q else "descriptive"

            if q_type == "mcq":
                return self._handle_mcq_answer(q, answer_text, choice_letter, spoken_msg)
            if q_type == "true_false":
                return self._handle_tf_answer(answer_text, spoken_msg)
            # descriptive / fill_blank / short_answer / long_answer
            return self._handle_descriptive_answer(q, answer_text, answer_action, spoken_msg)

        # ── CLARIFICATION ─────────────────────────────────────────────────────
        return {"action": "repeat_input", "message": spoken_msg}

    # ── MCQ ───────────────────────────────────────────────────────────────────
    def _handle_mcq_answer(self, q, answer_text: str, choice_letter, spoken_msg: str) -> Dict[str, Any]:
        """Validates MCQ answer and stages it. Format: 'A. Paris'."""
        options = (q or {}).get("options", {})

        letter      = None
        option_text = None

        if choice_letter and str(choice_letter).upper() in options:
            letter      = str(choice_letter).upper()
            option_text = options[letter]
        else:
            m = re.match(r'^([A-Ea-e])[.\s]+(.+)$', answer_text.strip())
            if m and m.group(1).upper() in options:
                letter      = m.group(1).upper()
                option_text = m.group(2).strip()
            else:
                lower_text = answer_text.strip().lower()
                for k, v in options.items():
                    if lower_text in v.lower() or v.lower() in lower_text:
                        letter      = k
                        option_text = v
                        break

        if not letter or not option_text:
            opts_text = ". ".join([f"Option {k}: {v}" for k, v in options.items()])
            return {
                "action": "repeat_input",
                "message": (f"That is not a valid option. "
                            f"The options are: {opts_text}. "
                            f"Please say Option A, B, C, or the option text."),
            }

        formatted = f"{letter}. {option_text}"
        spoken    = f"You selected Option {letter}, {option_text}. Is that correct?"
        self.state.set_pending(formatted, 1.0)
        self.state.previous_response_text = spoken
        return {
            "action": "answer_pending",
            "text":   formatted,
            "choice_letter": letter,
            "needs_confirmation": True,
            "prompt": spoken,
        }

    # ── True/False ────────────────────────────────────────────────────────────
    def _handle_tf_answer(self, answer_text: str, spoken_msg: str) -> Dict[str, Any]:
        lower = answer_text.strip().lower()
        if "true" in lower:
            tf = "True"
        elif "false" in lower:
            tf = "False"
        else:
            return {
                "action": "repeat_input",
                "message": "Please say True or False to answer this question.",
            }
        spoken = f"You said {tf}. Is that correct?"
        self.state.set_pending(tf, 1.0)
        self.state.previous_response_text = spoken
        return {
            "action": "answer_pending",
            "text":   tf,
            "needs_confirmation": True,
            "prompt": spoken,
        }

    # ── Descriptive / Fill-in-blank / Short / Long ────────────────────────────
    def _handle_descriptive_answer(self, q, answer_text: str,
                                    answer_action: str, spoken_msg: str) -> Dict[str, Any]:
        if not q or not answer_text.strip():
            return {"action": "repeat_input",
                    "message": "I didn't catch your answer. Please try again."}

        q_id     = q["id"]
        existing = self.state.get_answer(q_id) or ""

        if answer_action == "append":
            preview = f"{existing} {answer_text}".strip() if existing else answer_text
            prompt  = (f"Added. Full answer is now: {preview}. "
                       f"Do you want to modify anything else?")

        elif answer_action in ("replace", "replace_sentence"):
            preview = answer_text
            prompt  = (f"Updated answer: {preview}. "
                       f"Do you want to modify anything else?")

        elif answer_action in ("delete", "remove_sentence"):
            preview = answer_text if answer_text.strip() else existing
            if not answer_text.strip() and existing:
                sentences = [s.strip() for s in existing.split(".") if s.strip()]
                if sentences:
                    sentences.pop()
                preview = ". ".join(sentences) + ("." if sentences else "")
            prompt  = (f"Removed. Updated answer: {preview}. "
                       f"Do you want to modify anything else?")

        else:  # "new"
            preview = answer_text
            prompt  = (f'I heard: "{preview}". '
                       f'Shall I save this? Say yes to confirm, or no to re-answer.')

        self.state.set_pending(preview, 1.0)
        self.state.previous_response_text = prompt
        return {
            "action": "answer_pending",
            "text":   preview,
            "needs_confirmation": True,
            "prompt": prompt,
            "answer_action": answer_action,
        }

    # ── Commands ──────────────────────────────────────────────────────────────
    def _handle_command(self, cmd: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        spoken = meta.get("spoken_message", "")

        if cmd == "confirm":
            return {"action": "command", "command": "confirm", "message": spoken}

        if cmd == "change_answer":
            self.state.discard_pending()
            return {
                "action": "command",
                "command": "change_answer",
                "message": "No problem. Please tell me your answer again.",
            }

        if cmd == "status":
            return {"action": "status", "message": self.state.get_status_text()}

        if cmd == "review":
            return {"action": "command", "command": "review", "message": spoken}

        if cmd == "slow_speech":
            return {"action": "slow_speech", "message": "Speaking slower now."}

        if cmd == "fast_speech":
            return {"action": "fast_speech", "message": "Speaking faster now."}

        # Navigation and all other commands
        return {"action": "command", "command": cmd, "meta": meta, "message": spoken}
