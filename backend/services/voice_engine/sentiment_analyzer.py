"""
VaaniPariksha - Sentiment Analyzer
Detects student frustration or uncertainty through keyword patterns.
"""
import re
from typing import Dict, Any

class SentimentAnalyzer:
    def __init__(self):
        # Keywords suggesting frustration
        self.frustrated_keywords = [
            r"\b(frustrated|annoyed|stupid|dumb|wrong|no|not|pardon|repeat|again|hard|difficult|help)\b",
            r"\b(can'?t|cannot)\s+(do|hear|understand)\b",
            r"\b(what|how)\s+to\b",
            r"!+", # Multiple exclamation marks in transcript (some STT do this)
        ]
        
        # Keywords suggesting uncertainty/doubt
        self.uncertain_keywords = [
            r"\b(um|uh|maybe|i think|not sure|probably|perhaps|i guess|could be)\b",
            r"\s*\.\.\.\s*", # Long pauses/hesitations
        ]

    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analyzes the text for sentiment/intent markers.
        Returns: {score: float (0-1), category: str}
        """
        lower_text = text.lower().strip()
        
        frustration_hits = 0
        for pattern in self.frustrated_keywords:
            if re.search(pattern, lower_text):
                frustration_hits = frustration_hits + 1
                
        uncertainty_hits = 0
        for pattern in self.uncertain_keywords:
            if re.search(pattern, lower_text):
                uncertainty_hits = uncertainty_hits + 1
        
        # Determine category and simple score
        if frustration_hits > 1 or (frustration_hits > 0 and len(lower_text) < 10):
            return {"score": min(1.0, frustration_hits * 0.4), "category": "frustrated"}
        elif uncertainty_hits > 0:
            return {"score": min(0.8, uncertainty_hits * 0.3), "category": "uncertain"}
            
        return {"score": 0.0, "category": "neutral"}
