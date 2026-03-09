# VaaniPariksha 🎙

**Voice-Based Examination Platform** — Hackathon MVP Build

> Upload PDF → Parse Questions → Students Answer by Voice → Answer PDF Generated

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | Required |
| PostgreSQL | 14+ | Local or AWS RDS |
| Tesseract OCR | 5.x | Windows: [Download installer](https://github.com/UB-Mannheim/tesseract/wiki) |

### 1. Clone & Setup Environment

```powershell
cd vaanipariksha
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
copy .env.example .env
# Edit .env with your DB credentials
```

### 3. Setup Database

```powershell
# Create PostgreSQL DB
psql -U postgres -c "CREATE DATABASE vaanipariksha_db;"
psql -U postgres -d vaanipariksha_db -f backend/database/schema.sql
```

### 4. Download Vosk STT Model

```powershell
python download_vosk_model.py
# Downloads ~50MB vosk-model-small-en-us-0.15 to models_vosk/
```

### 5. Generate Sample Exam PDF

```powershell
python sample_exam/generate_sample_pdf.py
# Creates sample_exam/sample_exam.pdf with 14 questions
```

### 6. Run the Server

```powershell
python run.py
```

**Open**: http://localhost:5000

---

## 🎤 Hackathon Demo Flow

1. **Upload** → Go to `http://localhost:5000`, drop `sample_exam/sample_exam.pdf`
2. **Parse** → Questions auto-detected (MCQ, True/False, Fill-blank, Short, Long)
3. **Start Exam** → Click "Start Voice Exam", system reads Q1 aloud
4. **Navigate** → Say "Next question" / "Go to question 5" / "Repeat question"
5. **Answer** → Speak your answer; system confirms if confidence < 75%
6. **Status** → Say "Give me status" → system speaks progress summary
7. **Submit** → Click Submit → Answer-filled PDF generated → Download
8. **Admin** → Visit `http://localhost:5000/admin` for live dashboard

---

## 🔊 Voice Commands

| Command | Action |
|---------|--------|
| "Next question" | Navigate forward |
| "Previous question" | Navigate back |
| "Go to question 5" | Jump directly |
| "Repeat question" | Re-read current |
| "Skip question" | Mark as skipped |
| "Give me status" | Progress report |
| "Speed up" / "Slow down" | TTS rate control |
| "Submit" | End exam |
| "Confirm" | Confirm pending answer |
| "Repeat" | Discard and retry |

---

## 🏗 Architecture

```
vaanipariksha/
├── backend/
│   ├── app.py                    # Flask app factory
│   ├── config/settings.py        # All config from env
│   ├── database/db.py            # SQLAlchemy + connection
│   ├── database/schema.sql       # PostgreSQL schema
│   ├── models/models.py          # ORM: Exam, Question, Session, Response
│   ├── routes/upload.py          # POST /api/upload
│   ├── routes/exam.py            # /api/start-exam, /voice-command, etc.
│   ├── routes/admin.py           # /api/admin/dashboard
│   └── services/
│       ├── pdf_processor/        # Validation, parsing, OCR, DB writer
│       ├── voice_engine/         # TTS, STT, intent classifier, confidence layer
│       ├── session_manager/      # State, auto-save, crash recovery, timer
│       ├── answer_generator/     # ReportLab PDF output
│       └── security/             # AES-256, audio cleanup, session isolation
├── frontend/
│   ├── templates/                # index.html, exam.html, admin.html
│   └── static/
│       ├── css/style.css         # Premium dark-mode design system
│       └── js/                   # upload.js, exam.js, voice_indicator.js, admin.js
├── models_vosk/                  # Offline STT model (after download)
├── generated_pdfs/               # Output answer PDFs
├── uploads/                      # Uploaded exam PDFs
├── sample_exam/                  # Demo PDF + generator
├── tests/test_vaanipariksha.py   # Unit tests
├── run.py                        # Entry point
├── download_vosk_model.py        # One-time model setup
└── requirements.txt
```

---

## ☁️ AWS Integration

Set `STORAGE_MODE=aws` in `.env` to activate:

- **S3**: Uploaded PDFs and generated answer PDFs stored in S3
- **RDS**: PostgreSQL database on AWS RDS (Multi-AZ capable)

Required env vars: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_RDS_HOST`, etc.

---

## 🔒 Security Features

- ✅ AES-256-GCM encrypted responses in DB
- ✅ Temp audio file deletion after session
- ✅ Session isolation (per-session upload dirs)
- ✅ No external API calls (fully offline capable)
- ✅ Exam lockdown (copy/paste disabled, tab-switch detection)
- ✅ No answer evaluation — system is strictly capture-only

---

## 🧪 Run Tests

```powershell
python -m pytest tests/ -v
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload & parse exam PDF |
| POST | `/api/start-exam` | Start exam session |
| POST | `/api/voice-command` | Process voice input |
| POST | `/api/confirm-answer` | Confirm/repeat pending answer |
| POST | `/api/save-answer` | Save answer (keyboard fallback) |
| GET | `/api/status/<token>` | Get exam progress |
| GET | `/api/get-question/<token>` | Get current question |
| POST | `/api/submit-exam` | Submit & generate PDF |
| GET | `/api/download-pdf/<token>` | Download answer PDF |
| GET | `/api/admin/dashboard` | Admin panel data |
| GET | `/health` | Health check |
