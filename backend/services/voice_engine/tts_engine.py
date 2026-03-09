"""
VaaniPariksha - TTS Engine (pyttsx3 wrapper)
Text-to-speech with adjustable speed, volume, and context-aware reading.
"""
import threading
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TTSEngine:
    """Thread-safe TTS engine backed by pyttsx3."""

    def __init__(self, rate: int = 150, volume: float = 1.0):
        self._lock = threading.Lock()
        self._engine = None
        self.rate = rate
        self.volume = volume
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
            # Prefer a clearer voice if available
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "english" in v.name.lower() or "zira" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
            logger.info("TTS engine initialized.")
        except Exception as e:
            logger.error(f"TTS init failed: {e}")
            self._engine = None

    # ----------------------------------------------------------------------- #
    # Public methods
    # ----------------------------------------------------------------------- #

    def speak(self, text: str, block: bool = True):
        """Speak text. Blocks until done if block=True."""
        if not text or text.strip() == "":
            return
        if not self._engine:
            logger.warning("TTS engine unavailable. Text: " + text)
            return
        with self._lock:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS speak error: {e}")
                self._reinit()

    def speak_async(self, text: str):
        """Speak text without blocking the calling thread."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()

    def speak_question(self, question: dict):
        """Context-aware reading of a question dict."""
        q_type = question.get("question_type", "short_answer")
        q_num = question.get("question_number", "")
        q_text = question.get("question_text", "")
        options = question.get("options", {})

        intro = f"Question number {q_num}. "
        self.speak(intro)
        time.sleep(0.3)

        if q_type == "mcq":
            # Read question body (remove option text from it)
            body = self._strip_options(q_text)
            self.speak(body)
            time.sleep(0.4)
            if options:
                self.speak("The options are:")
                time.sleep(0.2)
                for key, val in options.items():
                    self.speak(f"Option {key}. {val}")
                    time.sleep(0.3)
        elif q_type == "true_false":
            self.speak("True or False. " + q_text)
        elif q_type == "long_answer":
            # For long questions, pause at sentence boundaries
            sentences = self._split_sentences(q_text)
            for i, sent in enumerate(sentences):
                self.speak(sent)
                if i < len(sentences) - 1:
                    time.sleep(0.4)
        else:
            self.speak(q_text)

    def set_rate(self, rate: int):
        """Adjust speech rate (words per minute). Clamp 75–350."""
        self.rate = max(75, min(350, rate))
        if self._engine:
            self._engine.setProperty("rate", self.rate)

    def set_speed_multiplier(self, multiplier: float):
        """Set speed as multiplier of 150 base rate. Range 0.5–2.0."""
        multiplier = max(0.5, min(2.0, multiplier))
        self.set_rate(int(150 * multiplier))

    def stop(self):
        """Stop current speech."""
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass

    def _reinit(self):
        """Re-initialize the engine after an error."""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
        except Exception as e:
            logger.error(f"TTS reinit failed: {e}")

    @staticmethod
    def _strip_options(text: str) -> str:
        """Remove option lines (A. B. C. D.) from question text."""
        import re
        return re.sub(r"[A-D][.)]\s+\S.*", "", text, flags=re.MULTILINE).strip()

    @staticmethod
    def _split_sentences(text: str) -> list:
        """Split text into sentences for paced delivery."""
        import re
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]


# Module-level singleton
_tts_instance: Optional[TTSEngine] = None


def get_tts_engine(rate: int = 150, volume: float = 1.0) -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine(rate=rate, volume=volume)
    return _tts_instance
