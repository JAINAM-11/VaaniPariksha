"""
VaaniPariksha - Sample Exam PDF Generator
Creates a demo PDF with multiple question types for hackathon demonstration.
Run: python sample_exam/generate_sample_pdf.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "sample_exam.pdf")


def generate():
    doc = SimpleDocTemplate(OUTPUT_PATH, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("Title", fontSize=18, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor("#1a237e"))
    sub_style = ParagraphStyle("Sub", fontSize=11, alignment=TA_CENTER, textColor=colors.HexColor("#546e7a"), spaceAfter=20)
    q_style = ParagraphStyle("Q", fontSize=11, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4)
    body_style = ParagraphStyle("Body", fontSize=10, leading=15, spaceAfter=4)
    opt_style = ParagraphStyle("Opt", fontSize=10, leftIndent=20, spaceAfter=2)

    story.append(Paragraph("Mid-Term Examination — Computer Science", title_style))
    story.append(Paragraph("Duration: 60 Minutes | Total Marks: 30 | All questions compulsory", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("SECTION A — Multiple Choice Questions (1 mark each)", ParagraphStyle("Sec", fontSize=12, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1565c0"))))

    questions = [
        # MCQ
        ("1.", "Which data structure uses LIFO (Last In First Out) principle?",
         ["A. Queue", "B. Stack", "C. Linked List", "D. Tree"], "mcq"),
        ("2.", "What is the time complexity of binary search?",
         ["A. O(n)", "B. O(n²)", "C. O(log n)", "D. O(1)"], "mcq"),
        ("3.", "Which sorting algorithm has the best average-case complexity?",
         ["A. Bubble Sort", "B. Insertion Sort", "C. Merge Sort", "D. Selection Sort"], "mcq"),
        # True/False
        ("4.", "True or False: A binary tree can have at most two children per node.", None, "true_false"),
        ("5.", "True or False: Python is a statically typed programming language.", None, "true_false"),
        ("6.", "True or False: HTTP is a stateless protocol.", None, "true_false"),
        # Fill blanks
        ("7.", "Fill in the blank: The process of converting source code into machine code is called ______.", None, "fill_blank"),
        ("8.", "Fill in the blank: IP stands for Internet ______.", None, "fill_blank"),
        # Short answer
        ("9.", "What is the difference between a compiler and an interpreter? (2 marks)", None, "short_answer"),
        ("10.", "Define recursion and give one real-world example. (2 marks)", None, "short_answer"),
        ("11.", "What is the purpose of an operating system? List any three functions. (3 marks)", None, "short_answer"),
        # Long answer
        ("12.", "Explain the concept of Object-Oriented Programming (OOP). Describe the four pillars of OOP with examples. (5 marks)", None, "long_answer"),
        ("13.", "Describe the OSI model and explain the role of each layer in data communication. (5 marks)", None, "long_answer"),
        # Sub-questions
        ("14.", "Answer the following sub-questions:", None, "short_answer"),
    ]

    sub_qs = [
        ("(a)", "What is a primary key in a database? Why is it important?"),
        ("(b)", "Differentiate between DDL and DML commands in SQL."),
        ("(c)", "Write a SQL query to find all students with marks greater than 80."),
    ]

    for num, text, opts, qtype in questions:
        if qtype == "mcq":
            story.append(Paragraph(f"{num} {text}", q_style))
            for opt in opts:
                story.append(Paragraph(opt, opt_style))
        elif qtype == "true_false":
            story.append(Paragraph(f"{num} {text}", q_style))
            story.append(Paragraph("(Write True or False below)", opt_style))
        elif qtype == "fill_blank":
            story.append(Paragraph(f"{num} {text}", q_style))
        elif qtype == "short_answer":
            story.append(Paragraph(f"{num} {text}", q_style))
            if num == "14.":
                for sub_num, sub_text in sub_qs:
                    story.append(Paragraph(f"{sub_num} {sub_text}", opt_style))
        elif qtype == "long_answer":
            story.append(Paragraph(f"{num} {text}", q_style))

        story.append(Spacer(1, 0.15*cm))

    doc.build(story)
    print(f"✅ Sample exam PDF generated: {OUTPUT_PATH}")
    print(f"   → {len(questions)} questions covering MCQ, True/False, Fill-blank, Short, Long answer + sub-questions")


if __name__ == "__main__":
    generate()
