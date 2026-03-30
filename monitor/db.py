"""
db.py — SQLite schema, connection helpers e queries base.
Localização do banco: %APPDATA%\ActivityMonitor\activity.db
"""

import sqlite3
import os
import json
import logging
from pathlib import Path
from datetime import date, datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------

def get_db_dir() -> Path:
    from monitor.config import get_settings
    cfg = get_settings()
    if cfg.get("db_dir"):
        p = Path(cfg["db_dir"])
    else:
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ActivityMonitor"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path() -> Path:
    return get_db_dir() / "activity.db"


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """Context manager que retorna uma conexão SQLite com row_factory."""
    conn = sqlite3.connect(get_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # suporte a múltiplos leitores
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,          -- ISO-8601 UTC
    process_name  TEXT,
    exe_path      TEXT,
    window_title  TEXT,
    url           TEXT,
    duration      INTEGER DEFAULT 10,        -- segundos
    is_idle       INTEGER DEFAULT 0          -- 1 = usuário ocioso
);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time    TEXT NOT NULL,
    end_time      TEXT NOT NULL,
    duration      INTEGER NOT NULL,
    process_name  TEXT,
    exe_path      TEXT,
    window_title  TEXT,
    url           TEXT,
    category      TEXT,
    is_productive INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT UNIQUE NOT NULL,  -- YYYY-MM-DD
    total_active_sec  INTEGER DEFAULT 0,
    total_idle_sec    INTEGER DEFAULT 0,
    top_apps          TEXT,                  -- JSON array
    category_breakdown TEXT,                 -- JSON object
    score             REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern      TEXT    UNIQUE NOT NULL,
    category     TEXT    NOT NULL,
    is_productive INTEGER DEFAULT 0,
    match_type   TEXT    DEFAULT 'glob'      -- 'glob', 'regex', 'exact'
);

CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    md_path    TEXT,
    html_path  TEXT,
    score      REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_process     ON events(process_name);
CREATE INDEX IF NOT EXISTS idx_sessions_start     ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_process   ON sessions(process_name);
CREATE INDEX IF NOT EXISTS idx_daily_date         ON daily_summaries(date);
"""


def init_db() -> None:
    """Cria tabelas e índices se ainda não existirem."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info("Banco de dados inicializado em %s", get_db_path())


# ---------------------------------------------------------------------------
# Helpers de escrita
# ---------------------------------------------------------------------------

def insert_event(
    timestamp: str,
    process_name: str,
    exe_path: str,
    window_title: str,
    url: str | None,
    duration: int,
    is_idle: bool,
) -> int:
    """Insere um evento bruto e retorna o ID gerado."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO events (timestamp, process_name, exe_path, window_title, url, duration, is_idle)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, process_name, exe_path, window_title, url, duration, int(is_idle)),
        )
        return cur.lastrowid or 0


def insert_session(
    start_time: str,
    end_time: str,
    duration: int,
    process_name: str,
    exe_path: str,
    window_title: str,
    url: str | None,
    category: str,
    is_productive: bool,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO sessions
                (start_time, end_time, duration, process_name, exe_path,
                 window_title, url, category, is_productive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                start_time, end_time, duration, process_name, exe_path,
                window_title, url, category, int(is_productive),
            ),
        )
        return cur.lastrowid


def upsert_daily_summary(
    day: str,
    total_active_sec: int,
    total_idle_sec: int,
    top_apps: list,
    category_breakdown: dict,
    score: float,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_summaries
                (date, total_active_sec, total_idle_sec, top_apps, category_breakdown, score)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_active_sec   = excluded.total_active_sec,
                total_idle_sec     = excluded.total_idle_sec,
                top_apps           = excluded.top_apps,
                category_breakdown = excluded.category_breakdown,
                score              = excluded.score
            """,
            (
                day,
                total_active_sec,
                total_idle_sec,
                json.dumps(top_apps, ensure_ascii=False),
                json.dumps(category_breakdown, ensure_ascii=False),
                score,
            ),
        )


def upsert_report(day: str, created_at: str, md_path: str, html_path: str, score: float) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reports (date, created_at, md_path, html_path, score)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                created_at = excluded.created_at,
                md_path    = excluded.md_path,
                html_path  = excluded.html_path,
                score      = excluded.score
            """,
            (day, created_at, md_path, html_path, score),
        )


# ---------------------------------------------------------------------------
# Helpers de leitura
# ---------------------------------------------------------------------------

def fetch_events_for_day(day: str) -> list[sqlite3.Row]:
    """Retorna todos os eventos de um dia (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{day}%",),
        ).fetchall()
    return rows


def fetch_sessions_for_day(day: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE start_time LIKE ? ORDER BY start_time",
            (f"{day}%",),
        ).fetchall()
    return rows


def fetch_daily_summary(day: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM daily_summaries WHERE date = ?", (day,)
        ).fetchone()


def fetch_recent_summaries(days: int = 7) -> list[sqlite3.Row]:
    """Retorna sumários dos últimos N dias."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM daily_summaries
            ORDER BY date DESC
            LIMIT ?
            """,
            (days,),
        ).fetchall()


def fetch_latest_report() -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM reports ORDER BY date DESC LIMIT 1"
        ).fetchone()


def fetch_report_for_day(day: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM reports WHERE date = ?", (day,)
        ).fetchone()
