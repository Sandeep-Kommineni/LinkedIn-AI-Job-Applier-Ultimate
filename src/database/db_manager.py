import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DBManager:
    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS job_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_site TEXT NOT NULL,
                company_name TEXT,
                job_title TEXT,
                url TEXT,
                result TEXT NOT NULL,
                skip_reason TEXT,
                skills TEXT,
                interest_score INTEGER,
                interest_reason TEXT,
                llm_time_seconds REAL,
                submitted_resume_path TEXT,
                executed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_site TEXT NOT NULL,
                company_name TEXT,
                job_title TEXT,
                job_url TEXT,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(file_path)
            );

            CREATE TABLE IF NOT EXISTS cover_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_site TEXT NOT NULL,
                company_name TEXT,
                job_title TEXT,
                job_url TEXT,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(file_path)
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_site TEXT NOT NULL,
                question TEXT NOT NULL,
                question_type TEXT,
                answer TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(job_site, question)
            );
        """
        )
        self._conn.commit()

    def insert_job_application(
        self,
        job_site: str,
        company_name: str | None,
        job_title: str | None,
        url: str | None,
        result: str,
        skip_reason: str | None = None,
        skills: list | None = None,
        interest_score: int | None = None,
        interest_reason: str | None = None,
        llm_time_seconds: float | None = None,
        submitted_resume_path: str | None = None,
        executed_at: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO job_applications
               (job_site, company_name, job_title, url, result, skip_reason, skills,
                interest_score, interest_reason, llm_time_seconds, submitted_resume_path, executed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_site,
                company_name,
                job_title,
                url,
                result,
                skip_reason,
                json.dumps(skills) if skills is not None else None,
                interest_score,
                interest_reason,
                llm_time_seconds,
                submitted_resume_path,
                executed_at or datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def insert_resume(
        self,
        job_site: str,
        company_name: str | None,
        job_title: str | None,
        job_url: str | None,
        file_path: str,
    ) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO resumes
               (job_site, company_name, job_title, job_url, file_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                job_site,
                company_name,
                job_title,
                job_url,
                file_path,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def insert_cover_letter(
        self,
        job_site: str,
        company_name: str | None,
        job_title: str | None,
        job_url: str | None,
        file_path: str,
    ) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO cover_letters
               (job_site, company_name, job_title, job_url, file_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                job_site,
                company_name,
                job_title,
                job_url,
                file_path,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def upsert_question(
        self,
        job_site: str,
        question: str,
        question_type: str | None,
        answer: Any,
    ) -> None:
        answer_str = json.dumps(answer) if isinstance(answer, list) else answer
        self._conn.execute(
            """INSERT INTO questions (job_site, question, question_type, answer, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(job_site, question) DO UPDATE SET
                   question_type=excluded.question_type,
                   answer=excluded.answer,
                   updated_at=excluded.updated_at""",
            (
                job_site,
                question,
                question_type,
                answer_str,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
