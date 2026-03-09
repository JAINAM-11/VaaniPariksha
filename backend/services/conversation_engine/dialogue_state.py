"""
VaaniPariksha - Dialogue State
Manages the current state of the conversation.
"""

class DialogueState:
    IDLE = "idle"
    ONBOARDING = "onboarding"
    EXAM_ACTIVE = "exam_active"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EDITING_ANSWER = "editing_answer"
    NAVIGATING = "navigating"
    CLARIFYING = "clarifying"

    def __init__(self):
        self.current = self.IDLE

    def transition_to(self, new_state: str):
        self.current = new_state

    def get_state(self) -> str:
        return self.current
