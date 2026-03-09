"""
VaaniPariksha - Confidence Confirmation Layer
If STT confidence is below threshold, system prompts for confirm/repeat.
"""
import logging
from typing import Optional, Tuple
from backend.services.voice_engine.tts_engine import get_tts_engine

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.75
MAX_RETRIES = 3


class ConfidenceLayer:
    """
    Wraps the STT pipeline with a confirmation loop.
    If confidence < threshold, speaks the heard text and asks to confirm.
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, tts=None, stt=None):
        self.threshold = threshold
        self.tts = tts or get_tts_engine()
        self.stt = stt  # Injected STT engine (optional, for microphone mode)

    # ----------------------------------------------------------------------- #
    # Core method
    # ----------------------------------------------------------------------- #
    def validate(
        self,
        transcript: str,
        confidence: float,
        context: str = "answer",
    ) -> Tuple[str, bool, str]:
        """
        Validate a transcript against confidence threshold.

        Args:
            transcript: The STT result
            confidence: Confidence score (0.0–1.0)
            context: "answer" or "command" (for logging)

        Returns:
            (validated_text, needs_confirmation, prompt_text)
            - validated_text: the transcript (same)
            - needs_confirmation: True if confidence < threshold
            - prompt_text: what to say to the user
        """
        if not transcript:
            prompt = "I didn't catch that. Please try again."
            return transcript, True, prompt

        if confidence >= self.threshold:
            return transcript, False, ""

        # Low confidence — build confirmation prompt
        prompt = (
            f"I heard: '{transcript}'. "
            f"Say Confirm to save, or Repeat to try again."
        )
        logger.info(
            f"Low confidence ({confidence:.2f} < {self.threshold}) for: '{transcript}'"
        )
        return transcript, True, prompt

    def build_confirm_response(self, transcript: str, confidence: float) -> dict:
        """
        Build the API response dict for a low-confidence result.
        Used by the Flask route.
        """
        _, needs_confirm, prompt = self.validate(transcript, confidence)
        return {
            "status": "pending_confirmation" if needs_confirm else "confirmed",
            "heard": transcript,
            "confidence": round(confidence, 3),
            "prompt": prompt,
            "needs_confirmation": needs_confirm,
        }


# Module singleton
_layer: Optional[ConfidenceLayer] = None


def get_confidence_layer(threshold: float = None) -> ConfidenceLayer:
    global _layer
    if _layer is None:
        from backend.config.settings import Config
        t = threshold or Config.STT_CONFIDENCE_THRESHOLD
        _layer = ConfidenceLayer(threshold=t)
    return _layer
