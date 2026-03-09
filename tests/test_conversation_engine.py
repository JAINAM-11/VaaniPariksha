import unittest
from unittest.mock import MagicMock, patch
from backend.services.conversation_engine.conversation_manager import ConversationManager
from backend.services.session_manager.session_state import SessionState

class TestConversationEngine(unittest.TestCase):
    def setUp(self):
        self.questions = [
            {"id": 1, "question_number": "1", "question_text": "What is photosynthesis?", "question_type": "descriptive"},
            {"id": 2, "question_number": "2", "question_text": "Capital of France?", "options": {"A": "Paris", "B": "London"}, "question_type": "mcq"}
        ]
        self.session = SessionState("test-token", 1, self.questions, 3600)
        self.mgr = ConversationManager(self.session)

    @patch('backend.services.conversation_engine.llm_conversation_client.LLMConversationClient.chat')
    def test_natural_navigation(self, mock_chat):
        # Mock "Let's move ahead"
        mock_chat.return_value = {
            "type": "command",
            "command": "next",
            "spoken_message": "Moving to next question.",
            "requires_confirmation": False
        }
        
        result = self.mgr.process_input("Let's move ahead", 0.95)
        self.assertEqual(result["action"], "command")
        self.assertEqual(result["command"], "next")

    @patch('backend.services.conversation_engine.llm_conversation_client.LLMConversationClient.chat')
    def test_answer_append(self, mock_chat):
        # Initial answer
        self.session.save_answer(1, "Photosynthesis uses sunlight.")
        
        # Mock "Add that it requires water."
        mock_chat.return_value = {
            "type": "edit",
            "answer_action": "append",
            "answer_text": "it requires water.",
            "spoken_message": "Added to your answer.",
            "requires_confirmation": True
        }
        
        result = self.mgr.process_input("Add that it requires water.", 0.95)
        self.assertEqual(result["action"], "answer_pending")
        self.assertEqual(result["answer_action"], "append")

    @patch('backend.services.conversation_engine.llm_conversation_client.LLMConversationClient.chat')
    def test_mcq_phonetic(self, mock_chat):
        self.session.move_next() # Move to MCQ
        
        # Mock "Option sea"
        mock_chat.return_value = {
            "type": "answer",
            "answer": "Paris",
            "answer_text": "Paris",
            "spoken_message": "Selected Paris.",
            "requires_confirmation": True,
            "meta": {"choice_letter": "A"}
        }
        
        result = self.mgr.process_input("Option A", 0.95)
        self.assertEqual(result["action"], "answer_pending")

if __name__ == '__main__':
    unittest.main()
