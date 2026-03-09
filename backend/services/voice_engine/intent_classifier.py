"""
VaaniPariksha - Intent Classifier
Lightweight NLP layer to classify spoken input into:
  - NAVIGATION  (next, previous, go to, skip, repeat, status)
  - ANSWER      (student's actual answer to a question)
  - CONTROL     (pause, speed up, slow down, stop)
"""
import re
import logging
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

# Intent class labels
INTENT_NAVIGATION = "navigation"
INTENT_ANSWER = "answer"
INTENT_CONTROL = "control"
INTENT_CONFIRM = "confirm"
INTENT_REPEAT_INPUT = "repeat_input"
INTENT_MCQ_CHOICE = "mcq_choice"

# --------------------------------------------------------------------------- #
# Keyword patterns for each intent
# --------------------------------------------------------------------------- #
MCQ_CHOICE_PATTERNS = r"\b(option|select|choice|pick)?\s*([A-D])\b"
NAVIGATION_PATTERNS: Dict[str, str] = {
    "next": r"\b(next|next question|move (on|forward|next)|proceed)\b",
    "previous": r"\b(previous|prev|go back|last question|back)\b",
    "goto": r"\b(go to|goto|jump to|move to|navigate to|switch to|question|number)\s+(?:question|number|q|#|\s)*(\d+[a-z]?)\b",
    "repeat": r"\b(repeat|say again|read again|what was|pardon|once more)\b",
    "skip": r"\b(skip|pass|leave|next one|skip this)\b",
    "status": r"\b(status|progress|how many|remaining|how much time|time left)\b",
    "submit": r"\b(submit|finish|done|end exam|complete)\b",
    "list_skipped": r"\b(tell me|which|list|what|show|say|read)?\s*(which|all|the)?\s*questions?\s*(are|is)?\s*(skipped|left|remaining|unanswered|pending)\b",
}

CONTROL_PATTERNS: Dict[str, str] = {
    "pause": r"\b(pause|hold|wait|stop speaking|quiet)\b",
    "resume": r"\b(resume|continue|go on|start)\b",
    "faster": r"\b(faster|speed up|too slow|quicker)\b",
    "slower": r"\b(slower|slow down|too fast|slow)\b",
    "volume_up": r"\b(louder|volume up|speak up)\b",
    "volume_down": r"\b(quieter|volume down|too loud|lower)\b",
}

CONFIRM_PATTERNS = r"\b(confirm|yes|correct|that's right|save it|okay|ok|affirmative)\b"
REPEAT_INPUT_PATTERNS = r"\b(repeat|no|wrong|again|redo|change|re-?enter|retry)\b"


# Edit patterns for descriptive answers
EDIT_PATTERNS: Dict[str, str] = {
    "add": r"\b(add|append|write|include|also|plus)\b",
    "change": r"\b(change|replace|fix|correct|instead (of|of\s+the))\b",
    "refine": r"\b(refine|polish|improve|better|clean up|grammar)\b",
}


def classify_intent(text: str) -> Tuple[str, str, dict]:
    """
    Classified with priority:
    1. Mandatory Navigation (Goto, Next, Prev, Skip)
    2. MCQ Choice
    3. Control Commands
    4. Confirm/Repeat (Turn-based logic)
    5. Long-form edits (Add/Change)
    6. Default: Answer
    """
    if not text:
        return INTENT_ANSWER, "answer", {"raw": ""}

    text_lower = text.lower().strip()

    # --- 1. Navigation (Higest Priority to prevent "Move to" being misclassified) ---
    for action, pattern in NAVIGATION_PATTERNS.items():
        m = re.search(pattern, text_lower)
        if m:
            meta = {}
            if action == "goto":
                target_match = re.search(r"(?:question|number|q)?\s*(\d+[a-z]?)", text_lower)
                if target_match:
                    meta["target"] = target_match.group(1)
            return INTENT_NAVIGATION, action, meta

    # --- 2. MCQ Choice ---
    m = re.search(MCQ_CHOICE_PATTERNS, text_lower)
    if m:
        letter = m.group(2).upper()
        return INTENT_MCQ_CHOICE, "choice", {"letter": letter, "raw": text}

    # --- 3. Control ---
    for action, pattern in CONTROL_PATTERNS.items():
        if re.search(pattern, text_lower):
            return INTENT_CONTROL, action, {}

    # --- 4. Confirm / Repeat (Wait for response logic) ---
    if re.search(CONFIRM_PATTERNS, text_lower):
        return INTENT_CONFIRM, "confirm", {}
    if re.search(REPEAT_INPUT_PATTERNS, text_lower):
        return INTENT_REPEAT_INPUT, "repeat_input", {}

    # --- 5. Long-form Edits (Specific keywords) ---
    for action, pattern in EDIT_PATTERNS.items():
        if re.search(pattern, text_lower):
            return INTENT_ANSWER, action, {"raw": text}

    # --- 6. Default: treat as answer ---
    return INTENT_ANSWER, "answer", {"raw": text}


def parse_navigation_target(text: str) -> str:
    """Extract question number from navigation command."""
    m = re.search(r"(?:question|q|number)?\s*(\d+[a-z]?)", text.lower())
    return m.group(1) if m else "1"
