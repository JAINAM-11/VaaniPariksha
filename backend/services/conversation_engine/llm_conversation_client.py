"""
VaaniPariksha - LLM Conversation Client
Uses google.generativeai (legacy SDK) to interpret student speech.
"""
import os
import json
import re
import logging
import google.generativeai as genai
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LLMConversationClient:
    def __init__(self):
        self.model = None
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set. LLM features disabled.")
            return
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("models/gemini-2.5-flash")
            logger.info("LLM client ready: models/gemini-2.5-flash")
        except Exception as e:
            logger.error(f"LLM init failed: {e}")

    def chat(self, prompt: str) -> Dict[str, Any]:
        """Send prompt to LLM and return parsed JSON. No caching."""
        if not self.model:
            logger.warning("LLM model not available, using fallback.")
            return self._fallback(prompt)
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            raw = (response.text or "").strip()
            logger.debug(f"LLM raw response: {raw[:300]}")
            return self._parse_json(raw)
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return self._fallback(prompt)

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        """Robustly parse JSON from LLM response."""
        text = raw.strip()
        # Strip markdown fences
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Extract first { ... } block
        m2 = re.search(r"\{[\s\S]*\}", text)
        if m2:
            try:
                return json.loads(m2.group(0))
            except json.JSONDecodeError:
                pass
        logger.error(f"Could not parse LLM JSON. Raw: {raw[:200]}")
        return self._fallback(raw)

    def _fallback(self, text: str) -> Dict[str, Any]:
        """Rule-based fallback. Searches ONLY short key phrases."""
        t = text.lower()
        # Only match if this looks like a short command, not a full prompt
        if len(t) < 60:
            if any(k in t for k in ["next question", "move forward", "go ahead"]):
                return {"type": "command", "command": "next", "answer_action": "none",
                        "spoken_message": "Moving to next question."}
            if any(k in t for k in ["go back", "previous question", "previous"]):
                return {"type": "command", "command": "previous", "answer_action": "none",
                        "spoken_message": "Going to previous question."}
            if any(k in t for k in ["yes", "confirm", "correct", "save that"]):
                return {"type": "command", "command": "confirm", "answer_action": "none",
                        "spoken_message": ""}
            if any(k in t for k in ["no", "wrong", "change", "redo"]):
                return {"type": "command", "command": "change_answer", "answer_action": "none",
                        "spoken_message": ""}
        return {
            "type": "clarification",
            "command": "none",
            "answer_action": "none",
            "spoken_message": "Sorry, I didn't understand that. Could you please repeat?",
            "requires_confirmation": False,
        }

    # ── Debug file helper ─────────────────────────────────────────────────────
    @staticmethod
    def _debug_log(section: str, content: str) -> None:
        """Append a debug entry to modification_debug.log for tracing LLM calls."""
        import os, datetime
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "modification_debug.log")
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[{ts}] {section}\n{'='*60}\n{content}\n")

    def modify_answer(self, previous_answer: str, instruction: str) -> str | None:
        """
        Calls the LLM to apply a modification instruction to a saved answer.
        Returns the updated answer string, or None if the instruction is not
        a valid modification (add/change/delete) or if the LLM call fails.
        JSON is always used for structured communication with the LLM.
        """
        if not self.model:
            logger.warning("LLM not available — cannot modify answer.")
            self._debug_log("SKIPPED — no model", f"previous_answer={previous_answer!r}\ninstruction={instruction!r}")
            return None
        try:
            prev = previous_answer or "(no previous answer)"

            # ── Prompt with explicit JSON schema ─────────────────────────────
            prompt = (
                "You are an answer editor for a voice examination system.\n"
                "A student recorded a voice answer and is now giving a spoken modification instruction.\n\n"
                f"CURRENT ANSWER:\n{prev}\n\n"
                f"STUDENT'S INSTRUCTION:\n{instruction}\n\n"
                "TASK:\n"
                "1. Decide if the instruction is asking to ADD, CHANGE, REPLACE, or DELETE content.\n"
                "2. If YES — apply the change and return the COMPLETE updated answer.\n"
                "3. If NO (e.g. it is a question, a random statement, or unclear) — set applied to false.\n\n"
                "VALID modification examples:\n"
                "  - 'change X to Y'  →  swap X for Y inside the answer\n"
                "  - 'replace X with Y'  →  same as above\n"
                "  - 'change my whole answer to X'  →  replace everything with X\n"
                "  - 'add X'  /  'also include X'  →  append X naturally\n"
                "  - 'remove X'  /  'delete X'  →  remove that part\n"
                "  - 'change the second sentence to X'  →  replace that specific sentence\n\n"
                "RULES for the answer:\n"
                "  - Return the COMPLETE updated answer text (not just the changed part)\n"
                "  - If instruction replaces everything, return only the new content\n"
                "  - If previous answer is empty/none, treat any instruction as the fresh answer\n"
                "  - Do NOT add explanations, quotes, or meta-text inside updated_answer\n\n"
                "Respond with ONLY this JSON — no markdown fences, no extra text:\n"
                '{"applied": true, "updated_answer": "complete updated answer here"}\n'
                "OR if instruction is not a modification:\n"
                '{"applied": false, "updated_answer": ""}\n'
            )

            # Log the full prompt going TO the LLM
            self._debug_log(
                "PROMPT SENT TO LLM",
                f"previous_answer : {previous_answer!r}\n"
                f"instruction     : {instruction!r}\n\n"
                f"--- FULL PROMPT ---\n{prompt}",
            )

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    temperature=0.1,
                    max_output_tokens=1024,
                ),
            )
            raw = (response.text or "").strip()
            logger.info(f"modify_answer RAW: {raw[:500]}")

            # Log the raw response FROM the LLM
            self._debug_log("RAW RESPONSE FROM LLM", raw)

            # ── Dedicated JSON parser (never calls _fallback) ─────────────────
            parsed = self._parse_modify_json(raw)

            # Log the parsed dict
            self._debug_log("PARSED DICT", str(parsed))

            if parsed is None:
                self._debug_log("RESULT", "FAIL — _parse_modify_json returned None")
                logger.warning(f"modify_answer: JSON parse failed. raw='{raw[:200]}'")
                return None

            applied = parsed.get("applied", True)  # default True for backward compat
            updated = (parsed.get("updated_answer") or "").strip()

            if not applied:
                self._debug_log("RESULT", f"NOT APPLIED — LLM said applied=false. updated_answer={updated!r}")
                logger.info("modify_answer: LLM says instruction is not a modification.")
                return None

            if updated and updated not in ("complete updated answer here", prev):
                self._debug_log("RESULT", f"SUCCESS — returning: {updated!r}")
                logger.info(f"modify_answer: OK — '{updated[:100]}'")
                return updated

            self._debug_log(
                "RESULT",
                f"FAIL — applied=True but updated_answer is empty or placeholder.\n"
                f"updated={updated!r}\nprev={prev!r}",
            )
            logger.warning(f"modify_answer: applied=True but updated_answer empty or placeholder.")
            return None

        except Exception as e:
            self._debug_log("EXCEPTION", str(e))
            logger.error(f"modify_answer failed: {e}", exc_info=True)
            return None

    def _parse_modify_json(self, raw: str) -> dict | None:
        """
        Dedicated JSON parser for modify_answer responses.
        Never calls _fallback() — returns None on failure instead.
        Tries 3 strategies:
          1. Direct json.loads
          2. Strip markdown fences then json.loads
          3. Regex extraction of applied + updated_answer fields
        """
        import json
        import re

        # Strategy 1: direct parse
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: strip markdown fences
        text = raw
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
        # Also strip a leading/trailing { ... } if surrounded by explanation
        m2 = re.search(r"\{[\s\S]*\}", text)
        if m2:
            try:
                return json.loads(m2.group(0))
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: regex field extraction (robust against special chars in answer)
        applied_match = re.search(r'"applied"\s*:\s*(true|false)', raw, re.IGNORECASE)
        answer_match  = re.search(r'"updated_answer"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        if answer_match:
            updated = answer_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
            applied = True
            if applied_match:
                applied = applied_match.group(1).lower() == "true"
            return {"applied": applied, "updated_answer": updated}

        logger.warning(f"_parse_modify_json: all strategies failed for: {raw[:200]}")
        return None

