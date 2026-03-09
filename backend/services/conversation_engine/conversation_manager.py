"""
VaaniPariksha - Conversation Manager
Main coordinator for conversational intelligence.
"""
import logging
import os
from typing import Dict, Any
from backend.services.conversation_engine.context_memory import ContextMemory
from backend.services.conversation_engine.dialogue_state import DialogueState
from backend.services.conversation_engine.llm_conversation_client import LLMConversationClient
from backend.services.conversation_engine.intent_router import IntentRouter

logger = logging.getLogger(__name__)

class ConversationManager:
    def __init__(self, session_state):
        self.state = session_state
        self.memory = ContextMemory()
        self.dialogue = DialogueState()
        self.llm_client = LLMConversationClient()
        self.router = IntentRouter(session_state)
        logger.info("ConversationManager initialized.")

    def process_input(self, text: str, stt_confidence: float) -> Dict[str, Any]:
        """Processes user voice input through the conversational layer."""
        try:
            # 1. Update Memory with Current Context
            q = self.state.current_question()
            if q:
                self.memory.set_question(q["id"])
            
            context = self.memory.get_context()
            exam_progress = self.state.get_progress_summary()
            
            # 2. Get LLM Interpretation
            from backend.services.voice_engine.prompts import CONVERSATIONAL_INTENT_PROMPT
            
            prompt = CONVERSATIONAL_INTENT_PROMPT.format(
                text=text,
                student_id=getattr(self.state, 'student_id', 'N/A'),
                question_number=q.get("question_number", "1") if q else "N/A",
                question_type=q.get("question_type", "descriptive") if q else "N/A",
                question_text=q.get("question_text", "") if q else "N/A",
                options=q.get("options", "N/A") if q else "N/A",
                previous_answer=self.state.get_answer(q["id"]) if q else "None",
                previous_response_text=self.state.previous_response_text,
                exam_progress=exam_progress,
                memory=context
            )
            
            llm_result = self.llm_client.chat(prompt)
            
            # 3. Update Memory with Intent
            self.memory.update(
                action=llm_result.get("type", "unknown"),
                command=llm_result.get("command"),
                answer=llm_result.get("answer_text") or llm_result.get("answer"),
                state=llm_result.get("state")
            )
            
            # 4. Route to Action
            result = self.router.route(llm_result)
            
            # 5. Log interaction
            self._log_interaction(text, llm_result, result)
            
            return result

        except Exception as e:
            logger.error(f"ConversationManager processing failed: {e}", exc_info=True)
            return {
                "action": "repeat_input",
                "message": "I'm sorry, I encountered an error. Could you please repeat that?"
            }

    def _log_interaction(self, text, llm_response, system_action):
        try:
            import os
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "conversation_flow.log")
            with open(log_file, "a") as f:
                import datetime
                timestamp = datetime.datetime.now().isoformat()
                f.write(f"[{timestamp}] STT: {text}\n")
                f.write(f"[{timestamp}] LLM: {llm_response}\n")
                f.write(f"[{timestamp}] ACTION: {system_action}\n")
                f.write("-" * 20 + "\n")
        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")

    def handle_interruption(self):
        """Called when barge-in is detected."""
        logger.info("Voice interruption detected. Stopping TTS.")
