"""
VaaniPariksha - STT Engine (Deepgram Cloud)
High-accuracy Speech-to-Text using Deepgram Nova-2.
"""
import os
import json
import logging
import requests
import io
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Load API Key from environment directly for maximum reliability
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

class STTEngine:
    """Cloud speech-to-text using Deepgram API."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.api_key = DEEPGRAM_API_KEY
        
        if not self.api_key:
            logger.error("DEEPGRAM_API_KEY is missing from environment variables!")

    def is_ready(self) -> bool:
        return bool(self.api_key)

    def listen_from_audio_data(self, audio_bytes: bytes) -> Tuple[str, float]:
        """
        Transcribe audio bytes using Deepgram.
        """
        if not self.api_key:
            return "STT Error: Missing API Key", 0.0

        if not audio_bytes:
            return "", 0.0

        try:
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language=en-IN"
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "audio/wav"
            }

            # Deepgram handles WAV headers automatically
            logger.info(f"Sending {len(audio_bytes)} bytes to Deepgram...")
            response = requests.post(url, headers=headers, data=audio_bytes, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Deepgram Error {response.status_code}: {response.text}")
                return f"Cloud Error: {response.status_code}", 0.0

            data = response.json()
            logger.info(f"Deepgram raw response: {json.dumps(data)}")
            results = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
            
            transcript = results.get("transcript", "").strip()
            confidence = results.get("confidence", 0.0)
            
            logger.info(f"Deepgram result: '{transcript}' (Confidence: {confidence})")
            return transcript, confidence

        except Exception as e:
            logger.error(f"Deepgram request failed: {e}")
            return "", 0.0


# Module-level singleton
_stt_instance: Optional[STTEngine] = None

def get_stt_engine() -> STTEngine:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = STTEngine()
    return _stt_instance
