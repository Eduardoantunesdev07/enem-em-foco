PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY,
    year INTEGER NOT NULL CHECK(year BETWEEN 2023 AND 2025),
    day INTEGER NOT NULL CHECK(day IN (1,2)),
    application TEXT NOT NULL DEFAULT 'regular',
    color TEXT NOT NULL DEFAULT 'azul',
    booklet INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    source_page TEXT NOT NULL,
    paper_url TEXT NOT NULL,
    key_url TEXT NOT NULL,
    paper_path TEXT NOT NULL,
    key_path TEXT NOT NULL,
    paper_sha256 TEXT NOT NULL,
    key_sha256 TEXT NOT NULL,
    UNIQUE(year,day,application,color)
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    exam_id INTEGER NOT NULL REFERENCES exams(id),
    number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 180),
    language TEXT NOT NULL CHECK(language IN ('comum','ingles','espanhol')),
    area TEXT NOT NULL CHECK(area IN ('linguagens','humanas','natureza','matematica')),
    correct_option TEXT CHECK(correct_option IN ('A','B','C','D','E')),
    cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
    page INTEGER NOT NULL CHECK(page > 0),
    UNIQUE(exam_id,number,language),
    CHECK((cancelled = 1 AND correct_option IS NULL) OR (cancelled = 0 AND correct_option IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    exam_id INTEGER NOT NULL REFERENCES exams(id),
    language TEXT NOT NULL CHECK(language IN ('ingles','espanhol')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    submitted_at TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK(status IN ('in_progress','submitted'))
);

CREATE TABLE IF NOT EXISTS answers (
    attempt_id TEXT NOT NULL REFERENCES attempts(id),
    question_id INTEGER NOT NULL REFERENCES questions(id),
    selected_option TEXT NOT NULL CHECK(selected_option IN ('A','B','C','D','E')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY(attempt_id,question_id)
);

CREATE TABLE IF NOT EXISTS error_notes (
    question_id INTEGER PRIMARY KEY REFERENCES questions(id),
    reason TEXT NOT NULL CHECK(reason IN ('conteudo','atencao','interpretacao','tempo')),
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions(exam_id,language,number);
CREATE INDEX IF NOT EXISTS idx_attempts_exam ON attempts(exam_id,status);
