"""
VaaniPariksha - Security Layer
AES-256 encryption for stored responses and audio cleanup.
"""
import os
import logging
import base64
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# AES-256 Encryption / Decryption
# --------------------------------------------------------------------------- #

def _get_key(raw_key: str = None) -> bytes:
    """Derive a 32-byte key from config."""
    from backend.config.settings import Config
    key_str = raw_key or Config.ENCRYPTION_KEY
    # Pad or truncate to exactly 32 bytes
    key_bytes = key_str.encode("utf-8")[:32]
    key_bytes = key_bytes.ljust(32, b"\x00")
    return key_bytes


def encrypt_answer(plaintext: str, raw_key: str = None) -> bytes:
    """
    Encrypt answer text using AES-256-GCM.
    Returns: nonce (12B) + tag (16B) + ciphertext, base64-encoded as bytes.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets

    if not plaintext:
        return b""
    key = _get_key(raw_key)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Prepend nonce for decryption
    combined = nonce + ciphertext
    return base64.b64encode(combined)


def decrypt_answer(encrypted_bytes: bytes, raw_key: str = None) -> str:
    """
    Decrypt an AES-256-GCM encrypted answer.
    Returns plaintext string.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not encrypted_bytes:
        return ""
    try:
        key = _get_key(raw_key)
        aesgcm = AESGCM(key)
        combined = base64.b64decode(encrypted_bytes)
        nonce = combined[:12]
        ciphertext = combined[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return ""


# --------------------------------------------------------------------------- #
# Audio file cleanup
# --------------------------------------------------------------------------- #

def delete_temp_audio(audio_dir: str = None):
    """
    Delete all temporary audio files (*.wav, *.webm, *.ogg) after a session.
    """
    if not audio_dir:
        from backend.config.settings import Config
        audio_dir = os.path.join(Config.BASE_DIR, "uploads", "audio")

    if not os.path.isdir(audio_dir):
        return

    deleted = 0
    for ext in ("*.wav", "*.webm", "*.ogg", "*.mp3"):
        for f in Path(audio_dir).glob(ext):
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Could not delete audio file {f}: {e}")

    logger.info(f"Deleted {deleted} temp audio files from {audio_dir}")


def secure_delete_file(path: str):
    """Overwrite a file with zeros before deleting (basic secure delete)."""
    try:
        if os.path.exists(path):
            size = os.path.getsize(path)
            with open(path, "wb") as f:
                f.write(b"\x00" * size)
            os.remove(path)
            logger.debug(f"Securely deleted: {path}")
    except Exception as e:
        logger.warning(f"Secure delete failed for {path}: {e}")


# --------------------------------------------------------------------------- #
# Session isolation
# --------------------------------------------------------------------------- #

def get_session_upload_dir(session_token: str) -> str:
    """Return an isolated upload directory for a session."""
    from backend.config.settings import Config
    session_dir = os.path.join(Config.UPLOAD_FOLDER, "sessions", session_token[:16])
    os.makedirs(session_dir, exist_ok=True)
    return session_dir
