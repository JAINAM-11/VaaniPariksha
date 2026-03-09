-- VaaniPariksha Database Schema
-- Run: psql -U postgres -d vaanipariksha_db -f schema.sql

-- Enums
CREATE TYPE exam_status AS ENUM ('pending', 'active', 'completed', 'archived');
CREATE TYPE question_type AS ENUM ('mcq', 'fill_blank', 'true_false', 'short_answer', 'long_answer');
CREATE TYPE session_status AS ENUM ('active', 'paused', 'submitted', 'crashed', 'recovered');
CREATE TYPE response_status AS ENUM ('answered', 'skipped', 'unanswered');

-- EXAMS table
CREATE TABLE IF NOT EXISTS exams (
    id              SERIAL PRIMARY KEY,
    exam_code       VARCHAR(12) UNIQUE NOT NULL DEFAULT gen_random_uuid()::TEXT,
    title           VARCHAR(255) NOT NULL DEFAULT 'Untitled Exam',
    original_filename VARCHAR(255),
    pdf_path        TEXT,           -- local FS path or S3 key
    storage_mode    VARCHAR(10) DEFAULT 'local',
    total_questions INTEGER DEFAULT 0,
    duration_minutes INTEGER DEFAULT 60,
    status          exam_status DEFAULT 'pending',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_exams_code ON exams(exam_code);
CREATE INDEX idx_exams_status ON exams(status);

-- QUESTIONS table
CREATE TABLE IF NOT EXISTS questions (
    id              SERIAL PRIMARY KEY,
    exam_id         INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    question_number VARCHAR(20) NOT NULL,   -- "1", "2a", "3.i"
    parent_number   VARCHAR(20),            -- for sub-questions
    question_type   question_type NOT NULL,
    question_text   TEXT NOT NULL,
    options         JSONB DEFAULT NULL,     -- MCQ: {"A":"..","B":"..","C":"..","D":".."}
    marks           NUMERIC(5,2) DEFAULT 1,
    page_number     INTEGER DEFAULT 1,
    position_data   JSONB DEFAULT '{}',     -- bbox coords for PDF overlay
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_questions_exam ON questions(exam_id);
CREATE INDEX idx_questions_number ON questions(exam_id, question_number);

-- SESSIONS table
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    session_token   VARCHAR(64) UNIQUE NOT NULL,
    exam_id         INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_name    VARCHAR(255) DEFAULT 'Anonymous',
    student_id      VARCHAR(100),
    status          session_status DEFAULT 'active',
    current_question_num VARCHAR(20) DEFAULT '1',
    start_time      TIMESTAMPTZ DEFAULT NOW(),
    end_time        TIMESTAMPTZ,
    duration_seconds INTEGER,
    time_remaining_seconds INTEGER,
    last_saved_at   TIMESTAMPTZ DEFAULT NOW(),
    session_data    JSONB DEFAULT '{}',     -- crash recovery snapshot
    generated_pdf_path TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_token ON sessions(session_token);
CREATE INDEX idx_sessions_exam ON sessions(exam_id);
CREATE INDEX idx_sessions_status ON sessions(status);

-- RESPONSES table
CREATE TABLE IF NOT EXISTS responses (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id     INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    answer_text     TEXT,
    answer_encrypted BYTEA,                 -- AES-256 encrypted version
    status          response_status DEFAULT 'unanswered',
    confidence_score NUMERIC(4,3),          -- STT confidence (0.000–1.000)
    confirmed       BOOLEAN DEFAULT FALSE,
    attempt_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, question_id)
);
CREATE INDEX idx_responses_session ON responses(session_id);
CREATE INDEX idx_responses_question ON responses(question_id);
CREATE INDEX idx_responses_status ON responses(session_id, status);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_exams_updated_at BEFORE UPDATE ON exams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_responses_updated_at BEFORE UPDATE ON responses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
