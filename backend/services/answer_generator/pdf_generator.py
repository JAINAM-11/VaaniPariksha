"""
VaaniPariksha - Answer PDF Generator
Uses ReportLab to create an answer-filled PDF from session responses.
Handles layout, overflow, and marks unanswered questions.
"""
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm

# --------------------------------------------------------------------------- #
# Style definitions
# --------------------------------------------------------------------------- #
def _build_styles():
    styles = getSampleStyleSheet()
    custom = {
        "title": ParagraphStyle(
            "ExamTitle",
            parent=styles["Title"],
            fontSize=20,
            spaceAfter=8,
            textColor=colors.HexColor("#1a237e"),
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            fontSize=11,
            spaceAfter=4,
            textColor=colors.HexColor("#546e7a"),
            alignment=TA_CENTER,
        ),
        "question_num": ParagraphStyle(
            "QNum",
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1565c0"),
            spaceBefore=10,
            spaceAfter=2,
        ),
        "question_text": ParagraphStyle(
            "QText",
            fontSize=10,
            fontName="Helvetica",
            spaceAfter=3,
            leading=14,
            alignment=TA_JUSTIFY,
        ),
        "mcq_option": ParagraphStyle(
            "MCQOpt",
            fontSize=10,
            leftIndent=15,
            spaceAfter=1,
        ),
        "answer_label": ParagraphStyle(
            "AnsLabel",
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#2e7d32"),
            spaceBefore=3,
        ),
        "answer_text": ParagraphStyle(
            "AnsText",
            fontSize=10,
            fontName="Helvetica",
            textColor=colors.HexColor("#1b5e20"),
            leftIndent=10,
            leading=14,
        ),
        "not_answered": ParagraphStyle(
            "NotAns",
            fontSize=10,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#b71c1c"),
            leftIndent=10,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
        ),
    }
    return custom


def generate_answer_pdf(
    output_path: str,
    exam_title: str,
    questions: List[Dict],
    answers: Dict[int, str],
    statuses: Dict[int, str],
    student_name: str = "Anonymous",
    student_id: str = "",
    exam_duration_minutes: int = 60,
) -> str:
    """
    Generate a filled answer PDF.

    Args:
        output_path: Absolute path for output PDF
        exam_title: Name of the exam
        questions: List of question dicts from DB
        answers: {question_id: answer_text}
        statuses: {question_id: 'answered'|'skipped'|'unanswered'}
        student_name: Student's name
        student_id: Student's ID
        exam_duration_minutes: Duration for display
    Returns:
        output_path on success
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    styles = _build_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    story = []

    # --- Header ---
    story.append(Paragraph("🎙 VaaniPariksha — Voice-Based Exam System", styles["title"]))
    story.append(Paragraph(f"Exam: {exam_title}", styles["subtitle"]))
    story.append(Spacer(1, 3 * mm))

    # --- Student info table ---
    info_data = [
        ["Student ID:", student_id or "—", "Date:", datetime.now().strftime("%d %b %Y")],
        ["Duration:", f"{exam_duration_minutes} minutes", "", ""],
    ]
    # Total width ~17cm (A4 is 21cm, 2cm margins on each side)
    info_table = Table(info_data, colWidths=[3.5 * cm, 5 * cm, 3.5 * cm, 5 * cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8eaf6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9fa8da")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 4 * mm))

    # --- Summary statistics ---
    total = len(questions)
    answered_count = sum(1 for s in statuses.values() if s == "answered")
    skipped_count = sum(1 for s in statuses.values() if s == "skipped")
    unanswered_count = total - answered_count - skipped_count

    summary_data = [
        ["Total Questions", "Answered", "Skipped", "Not Attempted"],
        [str(total), str(answered_count), str(skipped_count), str(unanswered_count)],
    ]
    summary_table = Table(summary_data, colWidths=[4.5 * cm] * 4)
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#e8f5e9")),
        ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#fff3e0")),
        ("BACKGROUND", (3, 1), (3, 1), colors.HexColor("#ffebee")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9fa8da")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6 * mm))

    # --- Questions & Answers ---
    for q in questions:
        q_id = q["id"]
        q_num = q.get("question_number", "?")
        q_text = q.get("question_text", "")
        q_type = q.get("question_type", "short_answer")
        q_options = q.get("options") or {}
        status = statuses.get(q_id, "unanswered")
        answer = answers.get(q_id, "")

        block = []

        # Question number + type badge
        type_label = {
            "mcq": "MCQ",
            "true_false": "True/False",
            "fill_blank": "Fill in Blank",
            "short_answer": "Short Answer",
            "long_answer": "Long Answer",
        }.get(q_type, "Short Answer")

        block.append(Paragraph(
            f"<b>Q{q_num}</b> <font size='8' color='#546e7a'>[{type_label}]</font>",
            styles["question_num"]
        ))
        block.append(Paragraph(_safe_text(q_text), styles["question_text"]))

        # MCQ options
        if q_type == "mcq" and q_options:
            for key, val in q_options.items():
                block.append(Paragraph(f"({key}) {_safe_text(val)}", styles["mcq_option"]))

        # Answer section
        if status == "answered" and answer:
            block.append(Paragraph("✔ Answer:", styles["answer_label"]))
            block.append(Paragraph(_safe_text(answer), styles["answer_text"]))
        elif status == "skipped":
            block.append(Paragraph("— Skipped by student", styles["not_answered"]))
        else:
            block.append(Paragraph("✗ Not Answered", styles["not_answered"]))

        block.append(Spacer(1, 2 * mm))
        block.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e0e0")))

        story.append(KeepTogether(block))

    # --- Footer ---
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated by VaaniPariksha | {datetime.now().strftime('%d %b %Y %H:%M')} | "
        "Answers captured via voice — no evaluation performed.",
        styles["footer"]
    ))

    doc.build(story)
    logger.info(f"Answer PDF generated: {output_path}")
    return output_path


def _safe_text(text: str) -> str:
    """Escape XML special characters for ReportLab."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
