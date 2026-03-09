"""
VaaniPariksha - Command Processor
Processes classified navigation/control commands for an active exam session.
"""
import logging
from typing import Dict, Any, Optional

from backend.services.voice_engine.intent_classifier import (
    INTENT_NAVIGATION, INTENT_ANSWER, INTENT_CONTROL,
    INTENT_CONFIRM, INTENT_REPEAT_INPUT, INTENT_MCQ_CHOICE, 
    classify_intent, NAVIGATION_PATTERNS
)
from backend.services.voice_engine.tts_engine import get_tts_engine
from backend.services.voice_engine.sentiment_analyzer import SentimentAnalyzer
from backend.services.voice_engine.llm_classifier import LLMClassifier
from backend.services.voice_engine.prompts import ANSWER_MODIFY_PROMPT

logger = logging.getLogger(__name__)


def _debug_log(section: str, content: str) -> None:
    """Append a debug entry to modification_debug.log for tracing LLM calls."""
    import os, datetime
    # Point to backend/logs/modification_debug.log
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "modification_debug.log")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n[{ts}] {section}\n{'='*60}\n{content}\n")


class CommandProcessor:
    """
    Processes voice commands during an exam session.
    Holds a reference to the active SessionState for navigation.
    """

    def __init__(self, session_state, tts=None):
        self.state = session_state          # SessionState instance
        self.tts = tts or get_tts_engine()
        from backend.services.conversation_engine.conversation_manager import ConversationManager
        self.conv_manager = ConversationManager(session_state)
        # Reuse the proven-working LLMClassifier singleton for answer modification
        self.llm_classifier = LLMClassifier()

    def process(self, text: str, confidence: float) -> Dict[str, Any]:
        """
        Main entry: Conversational Intelligence Flow.
        QA state-machine is handled first. Then direct pattern matching. Then LLM.
        """
        import re

        lower = text.lower().strip()
        qa_state = getattr(self.state, "qa_conv_state", None)

        # ══════════════════════════════════════════════════════════════════════
        # QA CONVERSATION STATE MACHINE  (runs before everything else)
        # States: awaiting_modify_yn | awaiting_modification |
        #         awaiting_save_yn   | awaiting_modify_or_remove
        # ══════════════════════════════════════════════════════════════════════

        if qa_state == "awaiting_modify_yn":
            # System asked "Do you want to modify anything? yes/no"
            if re.search(r"\b(yes|sure|okay|modify|change|edit|add|delete|remove|want)\b", lower):
                msg = "Sure. Please tell me what you would like to modify. You can say add, change, or delete."
                self.state.previous_response_text = msg
                self.state.qa_conv_state = "awaiting_modification"
                return {"action": "status", "message": msg}
            if re.search(r"\b(no|nothing|done|save|keep|good|fine)\b", lower):
                return self._qa_ask_final_save()
            # Not recognised — re-ask
            msg = self.state.previous_response_text or "Do you want to modify? Say yes or no."
            return {"action": "status", "message": msg}

        if qa_state == "awaiting_modification":
            # 1. Shorthand Interceptor: Allow commands to break through the loop immediately
            # Use the already defined is_shorthand (will move it up)
            word_count = len(lower.split())
            is_shorthand = word_count <= 6
            if is_shorthand:
                # Check for direct navigation commands
                for action, pattern in NAVIGATION_PATTERNS.items():
                    if re.search(pattern, lower):
                        self.state.qa_conv_state = None
                        self.state.discard_pending()
                        # Fall through to normal processing!
                        break
                else: # Only continue with LLM if no shorthand command found
                    pass
                if self.state.qa_conv_state is None:
                    # We broke out via break in for loop
                    pass
                else:
                    # Proceed to LLM
                    pass
            
            if self.state.qa_conv_state == "awaiting_modification":
                import json as _json, re as _re
                q = self.state.current_question()
                previous_answer = (
                    self.state.pending_answer
                    or (self.state.get_answer(q["id"]) if q else "")
                    or ""
                )
                prev = previous_answer or "(no previous answer)"

                # Build the modification prompt using the central template
                prompt = ANSWER_MODIFY_PROMPT.format(
                    previous_answer=prev,
                    instruction=text
                )

                _debug_log("PROMPT SENT TO LLM (QA MOD)", prompt)
                raw = self.llm_classifier.chat(prompt)
                _debug_log("RAW RESPONSE FROM LLM (QA MOD)", raw if raw else "(EMPTY RESPONSE)")

                # Parse the JSON response
                data: Dict[str, Any] = {}
                if raw and raw.strip():
                    try:
                        data = _json.loads(raw)
                    except:
                        # Minimal regex fallback for data
                        ua = _re.search(r'"updated_answer"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
                        applied_m = _re.search(r'"applied"\s*:\s*(true|false)', raw)
                        cmd_m = _re.search(r'"is_command"\s*:\s*(true|false)', raw)
                        if ua: data["updated_answer"] = str(ua.group(1))
                        if applied_m: data["applied"] = (applied_m.group(1).lower() == 'true')
                        if cmd_m: data["is_command"] = (cmd_m.group(1).lower() == 'true')

                # Check if LLM signaled a command
                if data.get("is_command"):
                    self.state.qa_conv_state = None
                    self.state.discard_pending()
                    # Fall through to normal processing
                    _debug_log("LLM SIGNALED COMMAND", "Breaking out of QA loop")
                else:
                    updated = data.get("updated_answer", "").strip()
                    applied = data.get("applied", True)
                    
                    if applied and updated and updated not in ("complete answer here", prev):
                        preview = updated
                        msg = (
                            f'Updated answer: "{preview}". '
                            f'Do you want to modify anything else? Say yes to modify, or no to save.'
                        )
                    else:
                        preview = previous_answer
                        msg = (
                            f'Sorry, I could not apply that change. Your answer is still: "{preview}". '
                            f'Do you want to try modifying again? Say yes or no.'
                        )
                    
                    self.state.set_pending(preview, confidence)
                    self.state.previous_response_text = msg
                    self.state.qa_conv_state = "awaiting_modify_yn"
                    return {
                        "action": "answer_pending",
                        "text": preview,
                        "needs_confirmation": True,
                        "prompt": msg,
                        "message": msg,
                    }

        if qa_state == "awaiting_save_yn":
            # System read out full answer and asked "Shall I save?"
            if re.search(r"\b(yes|correct|confirm|yep|okay|right|sure|save|affirmative)\b", lower):
                self.state.qa_conv_state = None
                return self._handle_confirm()
            if re.search(r"\b(no|wrong|change|different|again|nope|redo)\b", lower):
                msg = "Do you want to modify it or remove it entirely? Say modify to change it, or remove to delete it."
                self.state.previous_response_text = msg
                self.state.qa_conv_state = "awaiting_modify_or_remove"
                return {"action": "status", "message": msg}
            msg = self.state.previous_response_text or "Shall I save this? Say yes or no."
            return {"action": "status", "message": msg}

        if qa_state == "awaiting_modify_or_remove":
            # System asked "Modify it or remove it entirely?"
            if re.search(r"\b(modify|change|edit|update|yes)\b", lower):
                msg = "Sure. Please tell me what you would like to modify. You can say add, change, or delete."
                self.state.previous_response_text = msg
                self.state.qa_conv_state = "awaiting_modification"
                return {"action": "status", "message": msg}
            if re.search(r"\b(remove|delete|discard|erase|clear|no|nothing)\b", lower):
                q_now = self.state.current_question()
                if q_now:
                    q_id = q_now["id"]
                    self.state.answers.pop(q_id, None)
                    self.state.statuses[q_id] = "unanswered"
                    self.state.discard_pending()
                self.state.qa_conv_state = None
                msg = "Answer removed. You can give your answer again whenever you are ready."
                self.state.previous_response_text = msg
                return {"action": "change_answer", "message": msg}
            msg = self.state.previous_response_text or "Say modify to change it, or remove to delete it."
            return {"action": "status", "message": msg}

        # ══════════════════════════════════════════════════════════════════════
        # END QA STATE MACHINE — fall through to normal processing
        # ══════════════════════════════════════════════════════════════════════

        # 0. Try direct MCQ / True-False matching BEFORE calling LLM
        direct = self._try_direct_match(text, confidence)
        if direct:
            return direct

        # 1. Use the new Conversation Manager for natural interaction
        result = self.conv_manager.process_input(text, confidence)

        # 🎯 Standard Response Logic
        res_type = result.get("action") # IntentRouter returns 'action'
        spoken_msg = result.get("message", "I'm sorry, I didn't quite catch that.")

        # Store system's next message for context in the next turn
        self.state.previous_response_text = spoken_msg

        # Route based on conversation manager's decision
        if res_type == "command":
            cmd = result.get("command")
            if cmd == "confirm":
                return self._handle_confirm()
            if cmd == "change_answer":
                return self._handle_change_answer()
            return self._handle_navigation_v2(cmd, result.get("meta", {}))

        if res_type == "answer_pending":
            prompt = result.get("prompt") or result.get("message") or spoken_msg
            # Ensure previous_response_text is set for next-turn confirm detection
            if prompt:
                self.state.previous_response_text = prompt
            ans = result.get("text")
            ans_action = result.get("answer_action", "new")
            return {
                "action": "answer_pending",
                "text": ans,
                "message": prompt,
                "needs_confirmation": True,
                "prompt": prompt,
                "answer_action": ans_action,
                "choice_letter": result.get("choice_letter"),
            }

        if res_type == "status":
            return {"action": "status", "message": result.get("message", spoken_msg)}

        if res_type == "answer_saved":
            return {"action": "answer_saved", "text": result.get("text"), "message": spoken_msg}

        return {"action": "repeat_input", "message": spoken_msg}

    def _qa_ask_final_save(self) -> Dict[str, Any]:
        """Re-read the current answer and ask for final save confirmation."""
        q = self.state.current_question()
        q_id = q["id"] if q else None
        final_ans = (
            self.state.pending_answer
            or (self.state.get_answer(q_id) if q_id else "")
            or ""
        )
        msg = (
            f'Your answer is: "{final_ans}". '
            f'Shall I save this? Say yes to confirm, or no to make changes.'
        )
        if q and not self.state.pending_answer:
            self.state.set_pending(final_ans, 1.0)
        self.state.previous_response_text = msg
        self.state.qa_conv_state = "awaiting_save_yn"
        return {
            "action": "answer_pending",
            "text": final_ans,
            "needs_confirmation": True,
            "prompt": msg,
            "message": msg,
        }

    def _try_direct_match(self, text: str, confidence: float) -> Optional[Dict[str, Any]]:
        """Direct rule-based matching for MCQ, True/False, confirm/change, and common commands."""
        import re
        q = self.state.current_question()
        if not q:
            return None
        q_type = (q.get("question_type") or "").lower()
        lower = text.lower().strip()

        # ── Word Count Guard for False Positives ──────────────────────────────
        # If the transcript is long, it's almost certainly an answer, not a command.
        # Exceptions: GO TO commands which can be longer.
        word_count = len(lower.split())
        is_shorthand = word_count <= 6

        # ── Accessibility: speed controls ─────────────────────────────────────
        if is_shorthand:
            if re.search(r'\b(speak slower|slow down|slower|too fast|speed down)\b', lower):
                self.state.previous_response_text = "Speaking slower now."
                return {"action": "slow_speech", "message": "Speaking slower now."}
            if re.search(r'\b(speak faster|speed up|faster|too slow|quicker|speed up)\b', lower):
                self.state.previous_response_text = "Speaking faster now."
                return {"action": "fast_speech", "message": "Speaking faster now."}

        # ── Accessibility: review answers ─────────────────────────────────────
        if re.search(r'\b(review|read.*(my|all).*answer|review.*answer)\b', lower):
            return self._handle_review_answers()

        # ── Navigation shortcuts (only if short or very specific) ──────────────
        if is_shorthand:
            if re.search(r'\b(no changes|done|that.s all|satisfied|i.m done|all good)\b', lower):
                prev = (self.state.previous_response_text or "").lower()
                if any(k in prev for k in ["any more changes", "shall i save", "is that correct",
                                            "add, change", "add or remove", "updated answer"]):
                    return self._handle_navigation_v2("next", {})

        # ── Already-answered: "Would you like to change it?" response ──────────

        # ── Modify-or-Remove prompt (after user said 'no' at final save) ──────
        prev = (self.state.previous_response_text or "").lower()
        is_modify_or_remove_prompt = "modify it or remove it" in prev
        if is_modify_or_remove_prompt and is_shorthand:
            if re.search(r"\b(modify|change|edit|update|yes)\b", lower):
                msg = "Sure. Please tell me what you would like to modify. You can say add, change, or delete."
                self.state.previous_response_text = msg
                return {"action": "status", "message": msg}
            if re.search(r"\b(remove|delete|discard|erase|clear|no|nothing)\b", lower):
                q_now = self.state.current_question()
                if q_now:
                    q_id = q_now["id"]
                    self.state.answers.pop(q_id, None)
                    self.state.statuses[q_id] = "unanswered"
                    self.state.discard_pending()
                msg = "Answer removed. You can give your answer again whenever you're ready."
                self.state.previous_response_text = msg
                return {"action": "change_answer", "message": msg}

        # ── Confirm / Change (when system is awaiting answer confirmation) ─────
        prev = (self.state.previous_response_text or "").lower()
        is_awaiting_confirm = any(k in prev for k in [
            "is that correct", "is it correct", "shall i save",
            "you said", "you selected", "i heard",
            "is there anything you'd like",
            "no to make changes",
        ])
        if is_awaiting_confirm:
            # Confirmations are usually short "yes" / "no"
            if is_shorthand:
                if re.search(r"\b(yes|correct|confirm|yep|okay|right|sure|save|that's right|affirmative)\b", lower):
                    return self._handle_confirm()
                if re.search(r"\b(no|wrong|incorrect|change|different|again|nope|not that|redo)\b", lower):
                    if "shall i save" in prev or "no to make changes" in prev:
                        msg = "Do you want to modify it or remove it entirely? Say modify to change it, or remove to delete it."
                        self.state.previous_response_text = msg
                        return {"action": "status", "message": msg}
                    return self._handle_change_answer()

        # ── Universal navigation commands ──────────────────────────────────────
        # Only check these as shorthands to skip false positives in answers
        NAV_PATTERNS = [
            (r'\b(skip this|skip question|skip)\b',                           'skip'),
            (r'\b(next question|next one|move forward|go ahead)\b',           'next'),
            (r'\b(previous question|go back|last question|prev)\b',           'previous'),
            (r'\b(repeat question|read again|read the question|repeat)\b',    'repeat'),
            (r'\b(repeat options|read options|read the options)\b',           'repeat'),
            (r'\b(status|how many left|what question|time left|how much time)\b', 'status'),
            (r'\b(submit exam|finish exam|submit)\b',                         'submit'),
        ]
        if is_shorthand:
            for pat, cmd in NAV_PATTERNS:
                if re.search(pat, lower):
                    return self._handle_navigation_v2(cmd, {})
        
        # GoTo: "go to question 3" / "jump to question number 5"
        m_goto = re.search(r'\b(go to|goto|jump to|move to|navigate to|switch to|question|number)\s+(?:question|number|q|#|\s)*(\d+)\b', lower)
        if m_goto:
            return self._handle_navigation_v2('goto', {'target': int(m_goto.group(2))})

        # ── MCQ ───────────────────────────────────────────────────────────────
        if q_type == "mcq":
            options = q.get("options", {})
            if not options:
                return None

            PHONETIC = {"aye": "A", "bee": "B", "sea": "C", "see": "C",
                        "dee": "D", "ee": "E"}

            matched_letter = None

            m = re.search(r'\boption\s*([A-Ea-e])\b', lower)
            if m:
                matched_letter = m.group(1).upper()
            if not matched_letter:
                m = re.match(r'^([A-Ea-e])[.\s]*$', lower)
                if m:
                    matched_letter = m.group(1).upper()
            if not matched_letter:
                for ph, lt in PHONETIC.items():
                    if re.search(rf'\b{ph}\b', lower):
                        matched_letter = lt
                        break
            if not matched_letter:
                for k, v in options.items():
                    if v.lower() in lower or lower in v.lower():
                        matched_letter = k
                        break

            if matched_letter and matched_letter in options:
                matched_text = options[matched_letter]
                formatted    = f"{matched_letter}. {matched_text}"
                prompt_msg   = f"You selected Option {matched_letter}, {matched_text}. Is that correct?"
                self.state.set_pending(formatted, confidence)
                self.state.previous_response_text = prompt_msg
                return {
                    "action": "answer_pending",
                    "text": formatted,
                    "choice_letter": matched_letter,
                    "needs_confirmation": True,
                    "prompt": prompt_msg,
                    "message": prompt_msg,
                }
            
            # REMOVED Greedy fallback: If not matched, return None to allow the LLM
            # or other handlers to catch it (e.g. if the user said a command).
            return None

        # ── True / False ────────────────────────────────────────────────────────
        if q_type == "true_false":
            if re.search(r"\b(true|that's true|it is true)\b", lower):
                answer = "True"
            elif re.search(r"\b(false|that's false|it is false)\b", lower):
                answer = "False"
            else:
                # NON-GREEDY: allow fall through if not a clear True/False
                return None
            prompt_msg = f"You said {answer}. Is that correct?"
            self.state.set_pending(answer, confidence)
            self.state.previous_response_text = prompt_msg
            return {
                "action": "answer_pending",
                "text": answer,
                "needs_confirmation": True,
                "prompt": prompt_msg,
                "message": prompt_msg,
            }

        # ── Fill in the blank (GREEDY only if nothing else matched) ─────────────
        if q_type in ("fill_blank", "fill_in_blank", "fill_in_the_blank"):
            if len(lower) > 0:
                prompt_msg = f'I heard your answer as: "{text}". Is that correct?'
                self.state.set_pending(text, confidence)
                self.state.previous_response_text = prompt_msg
                return {
                    "action": "answer_pending",
                    "text": text,
                    "needs_confirmation": True,
                    "prompt": prompt_msg,
                    "message": prompt_msg,
                }

        # ── Descriptive / Short / Long / QA ───────────────────────────────────
        # Only handle fresh answers here. Modify/confirm states are handled
        # by the QA state machine at the top of process().
        if q_type in ("descriptive", "short_answer", "long_answer", "essay", "qa"):
            if len(lower) > 1:
                prompt_msg = (
                    f'I heard: "{text}". '
                    f'Do you want to modify anything? Say yes to modify, or no to save.'
                )
                self.state.set_pending(text, confidence)
                self.state.previous_response_text = prompt_msg
                self.state.qa_conv_state = "awaiting_modify_yn"
                return {
                    "action": "answer_pending",
                    "text": text,
                    "needs_confirmation": True,
                    "prompt": prompt_msg,
                    "message": prompt_msg,
                }

        return None


    def _handle_review_answers(self) -> Dict[str, Any]:
        """Build a spoken review of all answered questions."""
        parts = []
        for i, q in enumerate(self.state.questions):
            qid    = q.get("id")
            qnum   = q.get("question_number", i + 1)
            ans    = self.state.get_answer(qid)
            status = self.state.statuses.get(qid, "unanswered")
            if ans:
                parts.append(f"Question {qnum}: {ans}")
            elif status == "skipped":
                parts.append(f"Question {qnum}: skipped")
        if not parts:
            msg = "You have not answered any questions yet."
        else:
            msg = "Here are your answers. " + ". ".join(parts) + ". That was the review."
        return {"action": "status", "message": msg}

    def _handle_answer_input(self, text: str, confidence: float, edit_action: str = "answer", meta: dict = None) -> Dict[str, Any]:
        """Processes potential answer or edit command with Smart Editor support."""
        if not meta: meta = {}
        q = self.state.current_question()
        q_type = q.get("question_type", "descriptive").lower()
        existing_ans = self.state.get_answer(q["id"]) or ""
        
        # A. MCQ Logic (Prioritize LLM Choice)
        if q_type == "mcq":
            choice_text = meta.get("choice_text")
            letter = meta.get("choice_letter")
            if choice_text and letter:
                self.state.set_pending(choice_text, confidence)
                return {
                    "action": "answer_pending",
                    "text": choice_text,
                    "choice_letter": letter,
                    "confidence": confidence,
                    "needs_confirmation": True,
                    "prompt": f"You have selected {choice_text}. Is it correct?"
                }
        
        # B. Smart Editor for Descriptive questions (Change/Add)
        if q_type == "descriptive" and existing_ans:
            is_change = meta.get("is_change", False) or edit_action == "change"
            is_add = edit_action == "add" or "add " in text.lower()
            
            if is_change:
                self.state.set_pending(text, confidence)
                return {
                    "action": "answer_pending",
                    "text": text,
                    "confidence": confidence,
                    "needs_confirmation": True,
                    "prompt": f"You have changed your answer to: {text}. Is that correct?"
                }
            
            if is_add:
                new_ans = f"{existing_ans} {text}"
                self.state.set_pending(new_ans, confidence)
                return {
                    "action": "answer_pending",
                    "text": new_ans,
                    "confidence": confidence,
                    "needs_confirmation": True,
                    "prompt": f"I have added that to your answer. The full answer is now: {new_ans}. Is that correct?"
                }

        # C. Standard Answer Flow
        self.state.set_pending(text, confidence)
        msg = f"I heard: {text}. Is that correct?"
        if q_type == "descriptive" and existing_ans:
            msg = f"I heard: {text}. Do you want to replace your existing answer, or say 'Add' to append this to it?"

        return {
            "action": "answer_pending",
            "text": text,
            "confidence": confidence,
            "needs_confirmation": True,
            "prompt": msg
        }

    def _handle_mcq_choice(self, letter: str, raw_text: str, confidence: float) -> dict:
        """MCQ specific selection and confirmation."""
        q = self.state.current_question()
        if q and q.get("question_type") == "mcq" and q.get("options"):
            options = q["options"]
            if letter in options:
                choice_text = options[letter]
                return {
                    "action": "answer_pending",
                    "text": choice_text,
                    "choice_letter": letter,
                    "confidence": confidence,
                    "needs_confirmation": True,
                    "prompt": f"I heard: option {letter}, {choice_text}. Is that correct?"
                }
        
        # Fallback to standard answer
        return self._handle_answer_input(raw_text, confidence)

    def _format_question_speech(self, q: dict) -> str:
        """Format question text + options for TTS. Replaces underscores with 'blank'."""
        if not q:
            return ""
        import re as _re
        q_text = q.get('question_text', '')
        # Replace ___ (fill-in-blank indicators) with the word 'blank' for TTS
        q_text = _re.sub(r'_{2,}', 'blank', q_text)
        text = f"Question {q.get('question_number', '')}. {q_text}"
        if q.get("question_type") == "mcq" and q.get("options"):
            text += " The options are: "
            for letter, val in q["options"].items():
                text += f"Option {letter}: {val}. "
        elif q.get("question_type") == "true_false":
            text = f"True or False. {q_text}"
        return text

    def _get_proactive_guidance(self) -> str:
        """Returns helpful reminders about skipped or unanswered questions."""
        progress = self.state.get_progress()
        if progress.get("skipped", 0) > 0:
            # Find the first skipped question number in order
            for q in self.state.questions:
                if self.state.statuses.get(q["id"]) == 'skipped':
                    return f" FYI, you still have question {q['question_number']} skipped."
        return ""

    # ----------------------------------------------------------------------- #
    # Navigation handlers
    # ----------------------------------------------------------------------- #
    def _handle_navigation_v2(self, command: str, meta: dict) -> dict:
        """Navigation via voice commands."""
        # Fix: Always clean up state before moving
        if command in ["next", "previous", "goto", "skip"]:
            self._prepare_navigation()

        target = meta.get("target") or meta.get("target_question") or meta.get("question_number")

        def _build_q_msg(q):
            """Build spoken question text including already-answered context."""
            if not q:
                return ""
            q_id   = q.get("id")
            saved  = self.state.get_answer(q_id) if q_id else ""
            status = self.state.statuses.get(q_id, "unanswered")
            msg    = self._format_question_speech(q)
            if saved and status == "answered":
                msg = (f"You have already answered this question. "
                       f"The question is: {self._format_question_speech(q)} "
                       f"Your saved answer is: {saved}. "
                       f"Do you want to modify anything? Say yes to modify, or no to save.")
                # Enter the modification flow
                self.state.qa_conv_state = "awaiting_modify_yn"
                self.state.set_pending(saved, 1.0)
            return msg

        if command == "next":
            moved = self.state.move_next()
            q = self.state.current_question()
            if moved:
                msg = _build_q_msg(q)
                self.state.previous_response_text = msg
                return {"action": "navigate", "direction": "next", "question": q,
                        "answer": self.state.get_answer(q["id"]) if q else None,
                        "message": msg}
            return {"action": "end", "question": q,
                    "message": "This is the last question. Say submit to finish your exam."}

        elif command == "previous":
            moved = self.state.move_previous()
            q = self.state.current_question()
            if moved:
                msg = _build_q_msg(q)
                self.state.previous_response_text = msg
                return {"action": "navigate", "direction": "previous", "question": q,
                        "answer": self.state.get_answer(q["id"]) if q else None,
                        "message": msg}
            return {"action": "end", "question": q,
                    "message": "You are already at the first question."}

        elif command == "goto" and target:
            moved = self.state.go_to_question(str(target))
            q = self.state.current_question()
            if moved:
                msg = _build_q_msg(q)
                self.state.previous_response_text = msg
                return {"action": "navigate", "direction": "goto", "question": q,
                        "answer": self.state.get_answer(q["id"]) if q else None,
                        "message": msg}
            return {"action": "end", "question": q,
                    "message": f"Could not find question {target}."}

        elif command == "skip":
            self.state.mark_skipped(self.state.current_q_index)
            self.state.move_next()
            q = self.state.current_question()
            msg = _build_q_msg(q) if q else "End of exam."
            self.state.previous_response_text = msg
            return {"action": "navigate", "direction": "skip", "question": q,
                    "answer": self.state.get_answer(q["id"]) if q else None,
                    "message": f"Question skipped. {msg}"}

        elif command == "repeat":
            q = self.state.current_question()
            msg = self._format_question_speech(q)
            return {"action": "repeat", "question": q, "message": msg}

        elif command == "status":
            return {"action": "status", "message": self.state.get_status_text()}

        elif command == "review":
            return self._handle_review_answers()

        elif command == "submit":
            return {"action": "submit_pending",
                    "message": "Are you sure you want to submit your exam? Say yes to confirm."}

        elif command == "list_skipped":
            return self._handle_list_skipped()

        return {"action": "repeat_input",
                "message": "Sorry, I didn't understand that command. Please try again."}

    def _handle_list_skipped(self) -> Dict[str, Any]:
        """List the numbers of all skipped or unanswered questions."""
        skipped_nums = []
        for i, q in enumerate(self.state.questions):
            q_id = q.get("id")
            q_num = q.get("question_number", str(i + 1))
            status = self.state.statuses.get(q_id, "unanswered")
            if status in ("skipped", "unanswered"):
                skipped_nums.append(str(q_num))

        if not skipped_nums:
            msg = "Great news! You have no skipped or unanswered questions."
        else:
            if len(skipped_nums) == 1:
                msg = f"Question {skipped_nums[0]} is currently skipped."
            else:
                last = skipped_nums.pop()
                nums_text = ", ".join(skipped_nums) + f", and {last}"
                msg = f"The skipped questions are {nums_text}."
        
        self.state.previous_response_text = msg
        return {"action": "status", "message": msg}

    def _prepare_navigation(self):
        """
        Logic to handle the 'from' question before we move elsewhere.
        1. Auto-skip if unanswered.
        2. Discard any pending/unconfirmed answers.
        3. Reset conversation state.
        """
        q = self.state.current_question()
        if q:
            q_id = q["id"]
            current_status = self.state.statuses.get(q_id, "unanswered")
            # If not answered and move away, mark as skipped
            if current_status == "unanswered":
                self.state.mark_skipped(self.state.current_q_index)
        
        # Discard any pending confirmation
        self.state.discard_pending()
        # Reset QA state machine
        self.state.qa_conv_state = None

    # ----------------------------------------------------------------------- #
    # Control handlers
    # ----------------------------------------------------------------------- #
    def _handle_control(self, action: str) -> dict:
        if action == "faster":
            return {"action": "control", "control": "faster"}
        elif action == "slower":
            return {"action": "control", "control": "slower"}
        elif action == "pause":
            return {"action": "control", "control": "pause"}
        elif action == "resume":
            return {"action": "control", "control": "resume"}
        elif action == "volume_up":
            self.tts.volume = min(1.0, self.tts.volume + 0.1)
            if self.tts._engine:
                self.tts._engine.setProperty("volume", self.tts.volume)
            return {"action": "control", "control": "volume_up"}
        elif action == "volume_down":
            self.tts.volume = max(0.1, self.tts.volume - 0.1)
            if self.tts._engine:
                self.tts._engine.setProperty("volume", self.tts.volume)
            return {"action": "control", "control": "volume_down"}
        return {"action": "control", "control": action}

    def _handle_confirm(self) -> dict:
        """Final save confirmation — always saves and advances for all question types."""
        q = self.state.current_question()
        self.state.confirm_pending()
        guidance = self._get_proactive_guidance()

        # For all types: save and advance to next question
        moved = self.state.move_next()
        if moved:
            nq = self.state.current_question()
            msg = f"Answer saved.{guidance} {self._format_question_speech(nq)}"
            self.state.previous_response_text = msg
            return {"action": "navigate", "direction": "next",
                    "question": nq,
                    "answer": self.state.get_answer(nq["id"]) if nq else None,
                    "message": msg}
        else:
            msg = f"Answer saved. This was the last question.{guidance} Say submit when you are ready."
            self.state.previous_response_text = msg
            return {"action": "confirm", "message": msg}

    def _handle_repeat_input(self) -> dict:
        return {"action": "repeat_input", "message": "Please repeat your answer."}

    def _handle_change_answer(self) -> dict:
        """Discards the pending answer and asks the student to re-answer."""
        self.state.discard_pending()
        q = self.state.current_question()
        q_type = (q.get("question_type") or "descriptive").lower() if q else "descriptive"
        if q_type == "mcq" and q and q.get("options"):
            opts = ". ".join([f"Option {k}: {v}" for k, v in q["options"].items()])
            msg = f"No problem. Please choose an option. The options are: {opts}."
        elif q_type == "true_false":
            msg = "No problem. Please say True or False."
        else:
            msg = "No problem. Please tell me your answer again."
        return {"action": "change_answer", "message": msg}
