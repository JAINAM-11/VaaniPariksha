"""
VaaniPariksha - Context Memory
Tracks conversation history and state for LLM context.
"""
from typing import Optional, Dict, Any, List


class ContextMemory:
    def __init__(self):
        self.current_question: Optional[int] = None
        self.previous_question: Optional[int] = None
        self.last_action: Optional[str] = None
        self.last_answer: Optional[str] = None
        self.last_command: Optional[str] = None
        self.confirming_answer: bool = False           # True while waiting for yes/no
        self.previous_answer_sentences: List[str] = [] # Sentence list for QA edit context
        self.conversation_state: str = "idle"          # idle|answering|confirming|navigating
        self.history: list = []

    def update(self, action: str, command: Optional[str] = None,
               answer: Optional[str] = None, state: Optional[str] = None):
        """Updates the memory with the latest interaction."""
        self.last_action = action
        if command:
            self.last_command = command
        if answer:
            self.last_answer = answer
            self.previous_answer_sentences = [
                s.strip() for s in answer.split(".") if s.strip()
            ]
        if state:
            self.conversation_state = state
            self.confirming_answer = (state == "confirming")

        self.history.append({
            "action": action,
            "command": command,
            "answer": answer,
            "state": self.conversation_state,
        })
        if len(self.history) > 10:
            self.history.pop(0)

    def set_question(self, q_id: int):
        if self.current_question != q_id:
            self.previous_question = self.current_question
            self.current_question = q_id
            self.confirming_answer = False  # reset on question change

    def get_context(self) -> Dict[str, Any]:
        """Returns the current memory context for the LLM."""
        return {
            "current_question": self.current_question,
            "previous_question": self.previous_question,
            "last_action": self.last_action,
            "last_answer": self.last_answer,
            "last_command": self.last_command,
            "confirming_answer": self.confirming_answer,
            "conversation_state": self.conversation_state,
            "recent_history": self.history[-3:] if self.history else [],
        }

    def clear(self):
        self.__init__()
