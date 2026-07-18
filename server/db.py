"""SQLite storage. Stdlib only; WAL mode; one connection per operation."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

DATA_DIR = os.environ.get("CFSTUDIO_DATA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DB_PATH = os.path.join(DATA_DIR, "cfstudio.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  handle TEXT DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS problems (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL DEFAULT 'local',
  cf_contest_id INTEGER,
  cf_index TEXT,
  url TEXT DEFAULT '',
  title TEXT NOT NULL,
  rating INTEGER,
  tags TEXT NOT NULL DEFAULT '[]',
  time_limit_ms INTEGER NOT NULL DEFAULT 2000,
  memory_limit_mb INTEGER NOT NULL DEFAULT 256,
  statement_html TEXT NOT NULL DEFAULT '',
  input_spec_html TEXT NOT NULL DEFAULT '',
  output_spec_html TEXT NOT NULL DEFAULT '',
  note_html TEXT NOT NULL DEFAULT '',
  samples TEXT NOT NULL DEFAULT '[]',
  reference_solution TEXT DEFAULT '',
  reference_language TEXT DEFAULT 'python',
  created_at INTEGER NOT NULL,
  UNIQUE(cf_contest_id, cf_index)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'sample',
  language TEXT NOT NULL,
  verdict TEXT NOT NULL,
  passed INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  detail TEXT NOT NULL DEFAULT '[]',
  code TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_tests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  input TEXT NOT NULL,
  expected TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  validated INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, problem_id)
);
CREATE TABLE IF NOT EXISTS bookmarks (
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  label TEXT NOT NULL DEFAULT 'favorite',
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, problem_id)
);
CREATE TABLE IF NOT EXISTS cf_verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  cf_submission_id INTEGER NOT NULL,
  verdict TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT '',
  submitted_at INTEGER NOT NULL,
  UNIQUE(user_id, cf_submission_id)
);
CREATE TABLE IF NOT EXISTS ai_chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  problem_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id, problem_id);
CREATE INDEX IF NOT EXISTS idx_ai_tests ON ai_tests(user_id, problem_id);
"""


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def now():
    return int(time.time())


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("tags", "samples", "detail"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (ValueError, TypeError):
                pass
    return d


def problem_public(row, full=False):
    """Shape a problem row for the API. Reference solution is never exposed."""
    d = row_to_dict(row)
    if d is None:
        return None
    d.pop("reference_solution", None)
    d.pop("reference_language", None)
    if not full:
        for k in ("statement_html", "input_spec_html", "output_spec_html", "note_html", "samples"):
            d.pop(k, None)
    return d
