"""
VaaniPariksha - ID Cleaner Service
Uses LLM to clean and format alphanumeric Student IDs from STT transcripts.
"""
import logging
import re
from backend.services.voice_engine.llm_classifier import LLMClassifier

logger = logging.getLogger(__name__)

# ── Number word → digit lookup ──────────────────────────────────────────────
_ONES = {
    'zero':'0','one':'1','two':'2','three':'3','four':'4',
    'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
    'ten':'10','eleven':'11','twelve':'12','thirteen':'13','fourteen':'14',
    'fifteen':'15','sixteen':'16','seventeen':'17','eighteen':'18','nineteen':'19',
}
_TENS = {
    'twenty':'20','thirty':'30','forty':'40','fifty':'50',
    'sixty':'60','seventy':'70','eighty':'80','ninety':'90',
}

def _words_to_digits(text: str) -> str:
    """
    Convert spelled-out numbers to digit strings.
    e.g. "twenty four" -> "24", "five" -> "5", "one hundred and one" -> "101"
    Works in-place on individual words; compound tens handled first.
    """
    # Handle compound tens: "twenty four", "thirty-two", etc.
    def replace_compound(m):
        tens_word = m.group(1).lower()
        ones_word = m.group(2).lower()
        tens_digit = int(_TENS[tens_word])
        ones_digit = int(_ONES.get(ones_word, '0'))
        return str(tens_digit + ones_digit)

    # Regex: twenty[-\s]four, thirty-one, etc.
    tens_pattern = r'\b(' + '|'.join(_TENS.keys()) + r')[-\s]+(' + '|'.join(_ONES.keys()) + r')\b'
    text = re.sub(tens_pattern, replace_compound, text, flags=re.IGNORECASE)

    # Handle plain tens (e.g. "twenty" alone)
    for word, digit in _TENS.items():
        text = re.sub(rf'\b{word}\b', digit, text, flags=re.IGNORECASE)

    # Handle ones/teens
    for word, digit in _ONES.items():
        text = re.sub(rf'\b{word}\b', digit, text, flags=re.IGNORECASE)

    # Remove "hundred", "and" connectors
    text = re.sub(r'\b(hundred|and|a)\b', '', text, flags=re.IGNORECASE)

    return text


ID_CLEANING_PROMPT = """\
You are a precision data formatter for an examination system.
The student has spoken their Student ID, which has been converted to text by Speech-to-Text (STT).
Your job is to extract the intended alphanumeric Student ID.

### STRICT RULES:
1. NO SPACES: Remove all spaces and punctuation.
2. FORCE NUMERIC: Convert EVERY spelled-out number to its digit form.
   - "four" → "4",  "five" → "5",  "twenty four" → "24"
   - "one hundred and one" → "101"
   - You are FORBIDDEN from returning spelled-out number words.
3. ALPHANUMERIC ONLY: Remove all special characters, filler words like "my id is".
4. UPPERCASE: Return exactly and only the alphanumeric ID in uppercase.
5. If no valid ID is found, return "INVALID".

### EXAMPLES:
- "JAINAM four five"          → "JAINAM45"
- "zero zero seven X"        → "007X"
- "B bravo two four"         → "BBRAVO24"
- "one hundred and one A"    → "101A"
- "ten thirteen"             → "1013"
- "my ID is twenty four B"   → "24B"
- "five S seven"             → "5S7"
- "A twenty two"             → "A22"

### STUDENT INPUT (pre-processed):
"{text}"

### OUTPUT (ONLY the cleaned alphanumeric ID, nothing else):
"""


class IDCleaner:
    def __init__(self):
        self.llm = LLMClassifier()

    def clean_id(self, text: str) -> str:
        logger.info(f"Cleaning ID for text: {text!r}")

        # Pre-process: convert number words to digits before LLM and in fallback
        preprocessed = _words_to_digits(text)
        logger.info(f"Pre-processed text: {preprocessed!r}")

        prompt = ID_CLEANING_PROMPT.format(text=preprocessed)
        result = self.llm.chat(prompt)

        if isinstance(result, dict):
            cleaned_raw = str(result.get("id", result.get("text", "")))
        else:
            cleaned_raw = str(result)

        logger.info(f"Raw LLM response: {cleaned_raw!r}")

        # Strip to alphanumeric only
        cleaned = re.sub(r'[^a-zA-Z0-9]', '', cleaned_raw).upper()

        if not cleaned or "INVALID" in cleaned_raw.upper():
            logger.warning("LLM returned INVALID; using pre-processed fallback.")
            # Fallback: strip everything except alphanumeric from pre-processed text
            fallback = re.sub(r'[^a-zA-Z0-9]', '', preprocessed).upper()
            if fallback:
                logger.info(f"Fallback result: {fallback!r}")
                return fallback
            return "INVALID"

        logger.info(f"Cleaned result: {cleaned!r}")
        return cleaned
