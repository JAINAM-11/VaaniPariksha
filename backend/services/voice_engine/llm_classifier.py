"""
VaaniPariksha - LLM Classifier
Uses Google Gemini to interpret complex natural language commands.
"""
import os
import json
import logging
import google.generativeai as genai
from typing import Tuple, Dict
from backend.services.voice_engine.prompts import INTENT_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

class LLMClassifier:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not found. LLM Classifier will be disabled.")
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('models/gemini-2.5-flash')

    def classify(self, text: str, student_id: str = "N/A", question_number: str = "1", question_text: str = "", options: dict = None, question_type: str = "descriptive", existing_answer: str = "", previous_response_text: str = "", exam_progress: str = "") -> dict:
        """
        Interprets text using LLM and returns the structured JSON response.
        """
        if not self.model:
            return {}

        try:
            options_str = json.dumps(options) if options else "N/A"
            prompt = INTENT_CLASSIFICATION_PROMPT.format(
                text=text, 
                student_id=student_id,
                question_number=question_number,
                question_text=question_text, 
                options=options_str,
                question_type=question_type,
                previous_answer=existing_answer or "None",
                previous_response_text=previous_response_text or "N/A",
                exam_progress=exam_progress
            )
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    stop_sequences=[],
                    max_output_tokens=300,
                    temperature=0.1,
                )
            )
            
            raw_text = response.text.strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].strip()
                
            data = json.loads(raw_text)
            logger.info(f"LLM Interpretation: {data.get('type')}/{data.get('command')}")
            return data

        except Exception as e:
            logger.error(f"LLM Classification failed: {e}")
            return {}

    def correct_transcription(self, text: str, context: str = "") -> str:
        """
        Uses LLM to fix misheard words in uneven audio (accuracy correction).
        """
        if not self.model:
            return text

        try:
            from backend.services.voice_engine.prompts_refiner import VOICE_CORRECTION_PROMPT
            prompt = VOICE_CORRECTION_PROMPT.format(text=text, context=context)
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"LLM Transcription Correction failed: {e}")
            return text
    def chat(self, prompt: str) -> str:
        """
        Generic chat method that returns raw text.
        """
        if not self.model:
            return ""
        try:
            response = self.model.generate_content(prompt)
            # Check if response has text (blocked by safety?)
            try:
                return response.text.strip()
            except Exception as e:
                logger.warning(f"LLM Response has no text: {e}")
                return ""
        except Exception as e:
            logger.error(f"LLM Chat failed: {e}")
            return ""

llm_classifier = LLMClassifier()
