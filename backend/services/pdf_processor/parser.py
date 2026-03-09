"""
VaaniPariksha - PDF Parser
Extracts and structures questions from uploaded exam PDFs.
Uses PyMuPDF for text extraction with Tesseract OCR fallback.
"""
import os
import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Question type patterns
# --------------------------------------------------------------------------- #
MCQ_PATTERNS = [
    r"^[A-D]\.",               # A. B. C. D.
    r"^[A-D]\)",               # A) B) C) D)
    r"^\([A-D]\)",             # (A) (B) (C) (D)
    r"^Option\s+[A-D]",        # Option A
]
TRUE_FALSE_KEYWORDS = ["true or false", "state whether", "write true or false", "t/f"]
FILL_BLANK_KEYWORDS = ["fill in the blank", "fill in", "complete the following", "___", "______"]
LONG_ANSWER_KEYWORDS = ["explain", "describe", "discuss", "elaborate", "write an essay", "critically analyse"]
SHORT_ANSWER_KEYWORDS = ["briefly", "write short", "short note", "define", "list", "state"]

# Question boundary patterns
Q_BOUNDARY_PATTERNS = [
    r"^\s*Q\.?\s*(\d+[\.\)]?)",                 # Q1. Q2. (allow leading space)
    r"^\s*Question\s+(\d+[\.\)]?)",            # Question 1
    r"^\s*(\d+)\s*[\.\)]",                     # 1. 1)
    r"^\s*\((\d+)\)",                          # (1)
]

SUB_Q_PATTERNS = [
    r"^\(([a-z])\)",          # (a) (b)
    r"^([a-z])\.",            # a. b.
    r"^([a-z])\)",            # a) b)
    r"^\(([ivxlcdm]+)\)",     # (i) (ii) roman numerals
    r"^([ivxlcdm]+)\.",       # i. ii.
]


class PDFParser:
    def __init__(self, pdf_path: str, tesseract_cmd: str = None):
        self.pdf_path = pdf_path
        self.tesseract_cmd = tesseract_cmd or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        self.raw_text_by_page: List[str] = []
        self.questions: List[Dict] = []

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #
    def parse(self) -> List[Dict]:
        """Main entry point. Returns list of structured question dicts."""
        self._extract_text()
        full_text = "\n".join(self.raw_text_by_page)
        self.questions = self._extract_questions(full_text)
        return self.questions

    def get_metadata(self) -> Dict:
        """Extract PDF metadata."""
        try:
            import fitz
            doc = fitz.open(self.pdf_path)
            meta = doc.metadata or {}
            result = {
                "page_count": doc.page_count,
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
            }
            doc.close()
            return result
        except Exception as e:
            logger.warning(f"Metadata extraction failed: {e}")
            return {}

    # ----------------------------------------------------------------------- #
    # Text Extraction
    # ----------------------------------------------------------------------- #
    def _extract_text(self):
        """Extract text from all pages using PyMuPDF, fallback to Tesseract."""
        import fitz
        doc = fitz.open(self.pdf_path)
        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if not text or len(text) < 20:
                # Fallback: render page as image and OCR
                text = self._ocr_page(page, page_num)
            self.raw_text_by_page.append(text)
        doc.close()
        logger.info(f"Extracted text from {len(self.raw_text_by_page)} pages.")

    def _ocr_page(self, page, page_num: int) -> str:
        """Use Tesseract to OCR a single page image."""
        try:
            import pytesseract
            from PIL import Image
            import fitz

            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
            clip = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [clip.width, clip.height], clip.samples)
            text = pytesseract.image_to_string(img, lang="eng")
            logger.info(f"OCR applied to page {page_num + 1}")
            return text.strip()
        except Exception as e:
            logger.error(f"OCR failed for page {page_num + 1}: {e}")
            return ""

    # ----------------------------------------------------------------------- #
    # Question Extraction
    # ----------------------------------------------------------------------- #
    def _extract_questions(self, text: str) -> List[Dict]:
        """Split text into individual questions using LLM for high accuracy."""
        logger.info("Starting LLM-based question extraction...")
        
        try:
            from backend.services.voice_engine.llm_classifier import llm_classifier
            from backend.services.voice_engine.prompts import PDF_QUESTION_EXTRACTION_PROMPT
            import json

            # Clean text slightly to avoid token waste but keep structure
            cleaned_text = self._clean_text(text)
            
            # Call LLM
            prompt = PDF_QUESTION_EXTRACTION_PROMPT.format(text=cleaned_text)
            response = llm_classifier.model.generate_content(prompt)
            
            raw_json = response.text.strip()
            # Clean possible markdown fences
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:-3].strip()
            elif raw_json.startswith("```"):
                raw_json = raw_json[3:-3].strip()
            
            questions = json.loads(raw_json)
            
            # Ensure all required fields exist
            for i, q in enumerate(questions):
                q.setdefault("parent_number", None)
                q.setdefault("options", None)
                q.setdefault("marks", 1.0)
                q.setdefault("order", i + 1)
                q.setdefault("sub_questions", [])
            
            logger.info(f"LLM extracted {len(questions)} questions.")
            return questions

        except Exception as e:
            logger.error(f"LLM Question Extraction failed: {e}. Falling back to Regex.")
            return self._extract_questions_regex(text)

    def _extract_questions_regex(self, text: str) -> List[Dict]:
        """Original regex-based extraction (Fallback)."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        questions = []
        current_q = None
        current_lines = []
        q_counter = 0

        for i, line in enumerate(lines):
            q_match = self._match_question_boundary(line)
            if q_match:
                if current_q and current_lines:
                    current_q = self._finalize_question(current_q, current_lines, q_counter)
                    if current_q:
                        questions.append(current_q)
                        q_counter += 1
                current_q = {
                    "question_number": q_match,
                    "raw_lines": [],
                }
                line_text = re.sub(r"^[Q\.]?\s*\d+[\.\)]\s*", "", line, count=1).strip()
                current_lines = [line_text] if line_text else []
            elif current_q is not None:
                current_lines.append(line)

        # Finalize last question
        if current_q and current_lines:
            current_q = self._finalize_question(current_q, current_lines, q_counter)
            if current_q:
                questions.append(current_q)

        # Extract sub-questions
        questions = self._expand_sub_questions(questions)
        logger.info(f"Extracted {len(questions)} questions/sub-questions via Regex.")
        return questions

    def _match_question_boundary(self, line: str) -> Optional[str]:
        """Check if a line marks the start of a new question. Returns question number or None."""
        for pattern in Q_BOUNDARY_PATTERNS:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _finalize_question(self, q_stub: Dict, lines: List[str], order: int) -> Optional[Dict]:
        """Build complete question dict from accumulated lines."""
        if not lines:
            return None

        q_type, options, option_line_indices = self._classify_question(lines)
        
        # Filter out lines that were identified as MCQ options
        question_lines = [line for i, line in enumerate(lines) if i not in option_line_indices]
        text = " ".join(question_lines).strip()
        
        if len(text) < 5 and not options:
            return None

        return {
            "question_number": q_stub["question_number"],
            "parent_number": None,
            "question_type": q_type,
            "question_text": self._clean_text(text),
            "options": options,
            "marks": self._extract_marks(text),
            "order": order,
            "sub_questions": [],
        }

    def _classify_question(self, lines: List[str]):
        """Classify question type from its lines. Returns (type_str, options_dict, option_line_indices)."""
        text_lower = " ".join(lines).lower()

        # Check for MCQ options in lines
        options, option_line_indices = self._extract_mcq_options(lines)
        if options:
            return "mcq", options, option_line_indices

        # True/False
        if any(kw in text_lower for kw in TRUE_FALSE_KEYWORDS):
            return "true_false", None, []

        # Fill in the blank
        if any(kw in text_lower for kw in FILL_BLANK_KEYWORDS) or "___" in " ".join(lines):
            return "fill_blank", None, []

        # Long answer (check for key action words)
        if any(kw in text_lower for kw in LONG_ANSWER_KEYWORDS):
            return "long_answer", None, []

        # Short answer
        if any(kw in text_lower for kw in SHORT_ANSWER_KEYWORDS):
            return "short_answer", None, []

        # Default: short answer
        return "short_answer", None, []

    def _extract_mcq_options(self, lines: List[str]) -> Tuple[Optional[Dict], List[int]]:
        """Parse MCQ options from lines. Returns (options_dict, list_items_indices)."""
        options = {}
        option_indices = []
        
        # Pattern to find options anywhere in the line: Letter followed by . or )
        # e.g. "A. Option One  B. Option Two"
        option_finder = r"([A-D])[.)]\s+([^A-D\n]+?(?=(?:\s+[A-D][.)])|$))"

        for i, line in enumerate(lines):
            found_any = False
            # Check for multiple options on one line
            matches = re.findall(option_finder, line, re.IGNORECASE)
            if matches:
                for key, val in matches:
                    options[key.upper()] = val.strip()
                option_indices.append(i)
                found_any = True
            
            # Fallback for full-line options if findall missed it
            if not found_any:
                for pat in MCQ_PATTERNS:
                    if re.match(pat, line, re.IGNORECASE):
                        letter_match = re.search(r"([A-D])[.)]\s*", line, re.IGNORECASE)
                        if letter_match:
                            key = letter_match.group(1).upper()
                            value = line[letter_match.end():].strip()
                            options[key] = value
                            option_indices.append(i)
                        break
        
        if len(options) >= 2:
            return options, option_indices
        return None, []

    def _extract_marks(self, text: str) -> float:
        """Try to extract marks from question text, e.g. '[5 marks]', '(2 marks)'."""
        pattern = r"[\[\(]\s*(\d+(?:\.\d+)?)\s*marks?\s*[\]\)]"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return 1.0

    def _expand_sub_questions(self, questions: List[Dict]) -> List[Dict]:
        """
        Detect sub-questions within question text and expand them.
        Returns flat list with sub-questions as separate entries.
        """
        expanded = []
        for q in questions:
            # Look for sub-question markers inside question text
            sub_qs = self._split_sub_questions(q)
            if sub_qs:
                # Keep parent with empty text, add subs
                q["has_sub_questions"] = True
                expanded.append(q)
                expanded.extend(sub_qs)
            else:
                q["has_sub_questions"] = False
                expanded.append(q)
        return expanded

    def _split_sub_questions(self, q: Dict) -> List[Dict]:
        """Split a question into sub-questions if sub-question markers are found."""
        text = q["question_text"]
        lines = text.split(". ")  # rough split
        sub_qs = []
        current_sub = None
        current_lines = []

        for line in text.splitlines() if "\n" in text else [text]:
            for pat in SUB_Q_PATTERNS:
                m = re.match(pat, line.strip(), re.IGNORECASE)
                if m:
                    if current_sub and current_lines:
                        sub_qs.append(self._build_sub_question(
                            current_sub, current_lines, q["question_number"]
                        ))
                    current_sub = m.group(1)
                    current_lines = [line[m.end():].strip()]
                    break
            else:
                if current_sub is not None:
                    current_lines.append(line.strip())

        if current_sub and current_lines:
            sub_qs.append(self._build_sub_question(
                current_sub, current_lines, q["question_number"]
            ))

        return sub_qs

    def _build_sub_question(self, sub_label: str, lines: List[str], parent_num: str) -> Dict:
        text = " ".join(lines).strip()
        q_type, options, _ = self._classify_question(lines)
        return {
            "question_number": f"{parent_num}{sub_label}",
            "parent_number": parent_num,
            "question_type": q_type,
            "question_text": self._clean_text(text),
            "options": options,
            "marks": self._extract_marks(text),
            "order": 0,
            "sub_questions": [],
            "has_sub_questions": False,
        }

    def _clean_text(self, text: str) -> str:
        """Remove excessive whitespace and control characters."""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", text)
        return text.strip()
