"""لایه‌ی ذخیره‌سازی (SQLite).

همه‌ی توابع org_id می‌گیرند تا داده‌ی هر سازمان از بقیه جدا بماند.
برای انتقال به Supabase/Postgres فقط همین فایل باید بازنویسی شود.
"""
import sqlite3
from contextlib import contextmanager

import numpy as np

import config

DB_PATH = config.DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS assistants (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assistant_id INTEGER NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('file', 'url', 'text')),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'error')),
    error TEXT DEFAULT '',
    n_chunks INTEGER DEFAULT 0,
    embed_model TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assistant_id INTEGER NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    location TEXT DEFAULT '',
    content TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('ticket', 'session')),
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_assistant ON chunks(org_id, assistant_id);
CREATE INDEX IF NOT EXISTS ix_sources_assistant ON sources(org_id, assistant_id);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ---------- سازمان و کاربر ----------

def create_org_with_admin(org_name: str, username: str, display_name: str, password_hash: str) -> dict:
    with connect() as c:
        org_id = c.execute("INSERT INTO organizations (name) VALUES (?)", (org_name,)).lastrowid
        c.execute(
            "INSERT INTO users (org_id, username, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'admin')",
            (org_id, username, display_name, password_hash),
        )
    return get_user_by_username(username)


def get_user_by_username(username: str) -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT u.*, o.name AS org_name FROM users u JOIN organizations o ON o.id = u.org_id WHERE u.username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def username_exists(username: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None


def list_users(org_id: int) -> list[dict]:
    with connect() as c:
        return _rows(c.execute(
            "SELECT id, username, display_name, role, created_at FROM users WHERE org_id = ? ORDER BY id", (org_id,)
        ))


def create_user(org_id: int, username: str, display_name: str, password_hash: str, role: str) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO users (org_id, username, display_name, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            (org_id, username, display_name, password_hash, role),
        )


def delete_user(org_id: int, user_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM users WHERE org_id = ? AND id = ?", (org_id, user_id))


# ---------- دستیارها ----------

def list_assistants(org_id: int) -> list[dict]:
    with connect() as c:
        return _rows(c.execute(
            """SELECT a.*,
                      (SELECT COUNT(*) FROM sources s WHERE s.assistant_id = a.id) AS n_sources,
                      (SELECT COUNT(*) FROM chunks ch WHERE ch.assistant_id = a.id) AS n_chunks
               FROM assistants a WHERE a.org_id = ? ORDER BY a.id""",
            (org_id,),
        ))


def get_assistant(org_id: int, assistant_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM assistants WHERE org_id = ? AND id = ?", (org_id, assistant_id)).fetchone()
    return dict(row) if row else None


def create_assistant(org_id: int, name: str, description: str, system_prompt: str) -> int:
    with connect() as c:
        return c.execute(
            "INSERT INTO assistants (org_id, name, description, system_prompt) VALUES (?, ?, ?, ?)",
            (org_id, name, description, system_prompt),
        ).lastrowid


def update_assistant(org_id: int, assistant_id: int, name: str, description: str, system_prompt: str) -> None:
    with connect() as c:
        c.execute(
            "UPDATE assistants SET name = ?, description = ?, system_prompt = ? WHERE org_id = ? AND id = ?",
            (name, description, system_prompt, org_id, assistant_id),
        )


def delete_assistant(org_id: int, assistant_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM assistants WHERE org_id = ? AND id = ?", (org_id, assistant_id))


# ---------- منابع و تکه‌ها ----------

def create_source(org_id: int, assistant_id: int, kind: str, name: str, embed_model: str) -> int:
    with connect() as c:
        return c.execute(
            "INSERT INTO sources (org_id, assistant_id, kind, name, embed_model) VALUES (?, ?, ?, ?, ?)",
            (org_id, assistant_id, kind, name, embed_model),
        ).lastrowid


def set_source_status(source_id: int, status: str, error: str = "", n_chunks: int = 0) -> None:
    with connect() as c:
        c.execute(
            "UPDATE sources SET status = ?, error = ?, n_chunks = ? WHERE id = ?",
            (status, error, n_chunks, source_id),
        )


def list_sources(org_id: int, assistant_id: int) -> list[dict]:
    with connect() as c:
        return _rows(c.execute(
            "SELECT * FROM sources WHERE org_id = ? AND assistant_id = ? ORDER BY id DESC", (org_id, assistant_id)
        ))


def delete_source(org_id: int, source_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM sources WHERE org_id = ? AND id = ?", (org_id, source_id))


def add_chunks(org_id: int, assistant_id: int, source_id: int,
               items: list[tuple[str, str]], embeddings: np.ndarray) -> None:
    """items: لیست (location, content) هم‌ترتیب با embeddings."""
    emb = np.asarray(embeddings, dtype=np.float32)
    with connect() as c:
        c.executemany(
            """INSERT INTO chunks (org_id, assistant_id, source_id, idx, location, content, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (org_id, assistant_id, source_id, i, loc, text, emb[i].tobytes())
                for i, (loc, text) in enumerate(items)
            ],
        )


def count_org_chunks(org_id: int) -> int:
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM chunks WHERE org_id = ?", (org_id,)).fetchone()[0]


def chunks_signature(org_id: int, assistant_id: int) -> tuple:
    """برای تشخیص تغییر پایگاه دانش (و باطل کردن کش جستجو)."""
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(id), 0) FROM chunks WHERE org_id = ? AND assistant_id = ?",
            (org_id, assistant_id),
        ).fetchone()
    return tuple(row)


def load_chunks(org_id: int, assistant_id: int) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            """SELECT ch.id, ch.source_id, ch.location, ch.content, ch.embedding, s.name AS source_name
               FROM chunks ch JOIN sources s ON s.id = ch.source_id
               WHERE ch.org_id = ? AND ch.assistant_id = ? AND s.status = 'ready'
               ORDER BY ch.id""",
            (org_id, assistant_id),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
        out.append(d)
    return out
