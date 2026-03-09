"""VaaniPariksha - Tests: PDF Parser"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.pdf_processor.parser import PDFParser
from backend.services.pdf_processor.validator import validate_pdf, PDFValidationError


class TestPDFValidator:
    def test_missing_file_raises(self):
        with pytest.raises(PDFValidationError):
            validate_pdf("/nonexistent/file.pdf")

    def test_non_pdf_raises(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        with pytest.raises(PDFValidationError):
            validate_pdf(str(f))

    def test_too_large_raises(self, tmp_path):
        f = tmp_path / "big.pdf"
        # Write fake PDF header but with size check only
        f.write_bytes(b"%PDF-" + b"0" * 100)
        # Max 1 byte for this test
        with pytest.raises(PDFValidationError):
            validate_pdf(str(f), max_size_bytes=1)


class TestIntentClassifier:
    def test_navigation_next(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_NAVIGATION
        intent, action, _ = classify_intent("next question")
        assert intent == INTENT_NAVIGATION
        assert action == "next"

    def test_navigation_goto(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_NAVIGATION
        intent, action, meta = classify_intent("go to question 3")
        assert intent == INTENT_NAVIGATION
        assert action == "goto"
        assert meta.get("target") == "3"

    def test_navigation_skip(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_NAVIGATION
        intent, action, _ = classify_intent("skip this question")
        assert intent == INTENT_NAVIGATION
        assert action == "skip"

    def test_answer_intent(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_ANSWER
        intent, action, meta = classify_intent("The capital of India is New Delhi")
        assert intent == INTENT_ANSWER
        assert meta["raw"] == "The capital of India is New Delhi"

    def test_control_faster(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_CONTROL
        intent, action, _ = classify_intent("speed up please")
        assert intent == INTENT_CONTROL
        assert action == "faster"

    def test_confirm(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_CONFIRM
        intent, _, _ = classify_intent("confirm")
        assert intent == INTENT_CONFIRM

    def test_status(self):
        from backend.services.voice_engine.intent_classifier import classify_intent, INTENT_NAVIGATION
        intent, action, _ = classify_intent("give me status")
        assert intent == INTENT_NAVIGATION
        assert action == "status"


class TestConfidenceLayer:
    def test_high_confidence_passes(self):
        from backend.services.voice_engine.confidence_layer import ConfidenceLayer
        layer = ConfidenceLayer(threshold=0.75)
        text, needs_confirm, prompt = layer.validate("Hello world", 0.9)
        assert not needs_confirm
        assert prompt == ""

    def test_low_confidence_needs_confirm(self):
        from backend.services.voice_engine.confidence_layer import ConfidenceLayer
        layer = ConfidenceLayer(threshold=0.75)
        text, needs_confirm, prompt = layer.validate("mumbai", 0.5)
        assert needs_confirm
        assert "heard" in prompt.lower()

    def test_empty_transcript(self):
        from backend.services.voice_engine.confidence_layer import ConfidenceLayer
        layer = ConfidenceLayer(threshold=0.75)
        text, needs_confirm, prompt = layer.validate("", 0.9)
        assert needs_confirm


class TestSessionState:
    def _make_state(self):
        from backend.services.session_manager.session_state import SessionState
        questions = [
            {"id": 1, "question_number": "1", "question_text": "Q1", "question_type": "short_answer", "options": None, "marks": 1},
            {"id": 2, "question_number": "2", "question_text": "Q2", "question_type": "mcq", "options": {"A": "Yes", "B": "No"}, "marks": 2},
            {"id": 3, "question_number": "3", "question_text": "Q3", "question_type": "true_false", "options": None, "marks": 1},
        ]
        return SessionState("token123", 1, questions, 3600)

    def test_navigation_next(self):
        s = self._make_state()
        assert s.current_q_index == 0
        assert s.move_next()
        assert s.current_q_index == 1

    def test_navigation_prev_at_start(self):
        s = self._make_state()
        assert not s.move_previous()

    def test_goto(self):
        s = self._make_state()
        assert s.go_to_question("3")
        assert s.current_question()["question_number"] == "3"

    def test_save_answer(self):
        s = self._make_state()
        s.save_answer(1, "New Delhi", 0.95)
        assert s.answers[1] == "New Delhi"
        assert s.statuses[1] == "answered"

    def test_skip(self):
        s = self._make_state()
        s.mark_skipped(0)
        assert s.statuses[1] == "skipped"

    def test_progress(self):
        s = self._make_state()
        s.save_answer(1, "Test", 1.0)
        s.mark_skipped(1)
        p = s.get_progress()
        assert p["answered"] == 1
        assert p["skipped"] == 1
        assert p["unanswered"] == 1

    def test_snapshot_restore(self):
        s = self._make_state()
        s.save_answer(1, "Paris", 0.9)
        snap = s.to_snapshot()
        s2 = self._make_state()
        s2.restore_snapshot(snap)
        assert s2.answers.get(1) == "Paris"


class TestAESEncryption:
    def test_encrypt_decrypt(self):
        from backend.services.security.encryption import encrypt_answer, decrypt_answer
        import os
        os.environ.setdefault("ENCRYPTION_KEY", "TestKey1234567890TestKey1234567!")
        plaintext = "My answer is photosynthesis"
        encrypted = encrypt_answer(plaintext, "TestKey1234567890TestKey1234567!")
        assert encrypted != plaintext.encode()
        decrypted = decrypt_answer(encrypted, "TestKey1234567890TestKey1234567!")
        assert decrypted == plaintext

    def test_empty_encrypt(self):
        from backend.services.security.encryption import encrypt_answer
        result = encrypt_answer("")
        assert result == b""
