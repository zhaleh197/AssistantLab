"""لایه‌ی ذخیره‌سازی.

دو پشتیبان با یک رابط:
- Postgres / Supabase (با pgvector): وقتی DATABASE_URL تنظیم شده باشد — برای استفاده‌ی واقعی
- SQLite: توسعه‌ی محلی و تست‌ها، بدون نیاز به اینترنت

همه‌ی توابع org_id می‌گیرند تا داده‌ی هر سازمان از بقیه جدا بماند.
SQL مشترک با «?» نوشته می‌شود و برای Postgres به «%s» تبدیل می‌شود.
"""
import re
import sqlite3
import threading
import time
from contextlib import contextmanager

import numpy as np

import config
from core.text import tokenize

DB_PATH = config.DB_PATH
DATABASE_URL = config.DATABASE_URL
PG_SCHEMA = config.DB_SCHEMA
EMBED_DIMS = config.EMBED_DIMENSIONS


class DuplicateError(ValueError):
    pass


class ConfigError(RuntimeError):
    pass


def is_postgres() -> bool:
    return bool(DATABASE_URL)


SQLITE_SCHEMA = """
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
    answer_mode TEXT NOT NULL DEFAULT 'sources' CHECK (answer_mode IN ('sources', 'sources_and_general')),
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
CREATE TABLE IF NOT EXISTS public_usage (
    assistant_id INTEGER NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (assistant_id, day)
);
CREATE INDEX IF NOT EXISTS ix_chunks_assistant ON chunks(org_id, assistant_id);
CREATE INDEX IF NOT EXISTS ix_sources_assistant ON sources(org_id, assistant_id);
"""

# جدول‌ها در schema جداگانه ساخته می‌شوند؛ API خودکار Supabase فقط schema «public» را منتشر می‌کند
PG_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS {schema};
SET search_path TO {schema}, extensions, public;

CREATE TABLE IF NOT EXISTS organizations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS assistants (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    answer_mode TEXT NOT NULL DEFAULT 'sources' CHECK (answer_mode IN ('sources', 'sources_and_general')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assistant_id BIGINT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('file', 'url', 'text')),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'error')),
    error TEXT NOT NULL DEFAULT '',
    n_chunks INTEGER NOT NULL DEFAULT 0,
    embed_model TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chunks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assistant_id BIGINT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    -- توکن‌های یکسان‌سازی‌شده (core.text.tokenize) برای جستجوی کلیدواژه‌ای
    search_text TEXT NOT NULL DEFAULT '',
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED,
    embedding VECTOR({dims}) NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('ticket', 'session')),
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_assistant ON chunks(org_id, assistant_id);
CREATE INDEX IF NOT EXISTS ix_chunks_source ON chunks(source_id);
CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS ix_sources_assistant ON sources(org_id, assistant_id);
CREATE INDEX IF NOT EXISTS ix_assistants_org ON assistants(org_id);
CREATE INDEX IF NOT EXISTS ix_users_org ON users(org_id);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_user ON auth_tokens(user_id);
CREATE TABLE IF NOT EXISTS public_usage (
    assistant_id BIGINT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (assistant_id, day)
);
"""

# مهاجرت: ستون‌هایی که بعد از ساخت اولیه‌ی جدول‌ها اضافه شده‌اند (برای هر دو دیتابیس)
COLUMN_MIGRATIONS = [
    ("assistants", "answer_mode",
     "TEXT NOT NULL DEFAULT 'sources' CHECK (answer_mode IN ('sources', 'sources_and_general'))"),
    # آدرس اختصاصی سازمان (?org=slug)
    ("organizations", "slug", "TEXT"),
    # لینک عمومی دستیار (?a=token)؛ NULL یعنی خاموش
    ("assistants", "public_token", "TEXT"),
    ("assistants", "public_daily_limit", "INTEGER NOT NULL DEFAULT 200"),
    # سؤال‌های پیشنهادی صفحه‌ی خوش‌آمد گفتگو (هر خط یک سؤال)
    ("assistants", "starter_questions", "TEXT NOT NULL DEFAULT ''"),
]
INDEX_MIGRATIONS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_organizations_slug ON organizations(slug) WHERE slug IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_assistants_public_token ON assistants(public_token) "
    "WHERE public_token IS NOT NULL",
]


# ---------- اتصال ----------

class _Conn:
    """رابط یکسان روی sqlite3 و psycopg."""

    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def execute(self, sql: str, params=()):
        return self.raw.execute(self._sql(sql), params)

    def executemany(self, sql: str, seq) -> None:
        if self.pg:
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), seq)
        else:
            self.raw.executemany(sql, seq)


_lock = threading.Lock()
_pool = None
_initialized: set = set()


def _validate_pg_config() -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", PG_SCHEMA):
        raise ConfigError("DB_SCHEMA فقط می‌تواند حروف کوچک انگلیسی، عدد و _ داشته باشد.")
    if ":6543" in DATABASE_URL:
        raise ConfigError(
            "آدرس Transaction pooler (پورت 6543) پشتیبانی نمی‌شود؛ "
            "در Supabase آدرس «Session pooler» (پورت 5432) را در DATABASE_URL بگذارید."
        )


def _create_pg_schema() -> None:
    import psycopg

    _validate_pg_config()
    with psycopg.connect(DATABASE_URL, autocommit=True, prepare_threshold=None) as conn:
        conn.execute(PG_SCHEMA_SQL.format(schema=PG_SCHEMA, dims=EMBED_DIMS))
        for table, column, ddl in COLUMN_MIGRATIONS:
            conn.execute(f"ALTER TABLE {PG_SCHEMA}.{table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        conn.execute(f"SET search_path TO {PG_SCHEMA}, extensions, public")
        for sql in INDEX_MIGRATIONS:
            conn.execute(sql)
        row = conn.execute(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'embedding'",
            (f"{PG_SCHEMA}.chunks",),
        ).fetchone()
    if row and row[0] != EMBED_DIMS:
        raise ConfigError(
            f"ابعاد بردار در دیتابیس ({row[0]}) با EMBED_DIMENSIONS ({EMBED_DIMS}) یکی نیست. "
            "یا EMBED_DIMENSIONS را برگردانید، یا جدول chunks را پاک کنید و منابع را دوباره اضافه کنید."
        )


def _configure_pg(conn) -> None:
    from pgvector.psycopg import register_vector

    conn.execute(f"SET search_path TO {PG_SCHEMA}, extensions, public")
    register_vector(conn)


# هر رفت‌وبرگشت به سرور سوپابیس ~۱۰۰+ میلی‌ثانیه است؛ اتصالی که تازه استفاده شده دوباره بررسی نمی‌شود
_CHECK_AFTER_IDLE = 30


def _check_pg(conn) -> None:
    from psycopg_pool import ConnectionPool

    if time.monotonic() - getattr(conn, "_al_used", 0) > _CHECK_AFTER_IDLE:
        ConnectionPool.check_connection(conn)


def _get_pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                _pool = ConnectionPool(
                    DATABASE_URL, min_size=1, max_size=5, open=True, timeout=30,
                    # اتصال‌های بیکار را pooler سوپابیس ممکن است ببندد؛ زودتر عوضشان می‌کنیم
                    max_idle=60, max_lifetime=30 * 60, reconnect_timeout=60,
                    # autocommit: هر دستور یک رفت‌وبرگشت؛ تراکنش فقط جایی که لازم است (connect(transaction=True))
                    kwargs={
                        "row_factory": dict_row, "prepare_threshold": None, "autocommit": True,
                        "connect_timeout": 10,
                        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3,
                    },
                    configure=_configure_pg, check=_check_pg,
                )
    return _pool


def reset() -> None:
    """بستن اتصال‌ها و فراموش کردن وضعیت راه‌اندازی (برای تست‌ها و تغییر تنظیمات)."""
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
        _initialized.clear()


@contextmanager
def connect(transaction: bool = False):
    """transaction=True برای چند دستور که باید با هم انجام شوند (در SQLite همیشه تراکنشی است)."""
    if is_postgres():
        with _get_pool().connection() as raw:
            try:
                if transaction:
                    with raw.transaction():
                        yield _Conn(raw, pg=True)
                else:
                    yield _Conn(raw, pg=True)
            finally:
                raw._al_used = time.monotonic()
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    try:
        yield _Conn(raw, pg=False)
        raw.commit()
    finally:
        raw.close()


def init_db() -> None:
    """ساخت جدول‌ها؛ در هر پروسه فقط یک بار برای هر دیتابیس اجرا می‌شود."""
    key = (DATABASE_URL, PG_SCHEMA) if is_postgres() else str(DB_PATH)
    if key in _initialized:
        return
    with _lock:
        if key in _initialized:
            return
        if is_postgres():
            _create_pg_schema()
        else:
            with connect() as c:
                c.raw.executescript(SQLITE_SCHEMA)
                for table, column, ddl in COLUMN_MIGRATIONS:
                    existing = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
                    if column not in existing:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                for sql in INDEX_MIGRATIONS:
                    c.execute(sql)
        _initialized.add(key)


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def retry_on_disconnect(fn, attempts: int = 2):
    """اجرای دوباره‌ی یک عملیات تکرارپذیر اگر اتصال به Postgres وسط کار قطع شود."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            disconnected = type(e).__name__ in ("OperationalError", "PoolTimeout") and is_postgres()
            if not disconnected or i == attempts - 1:
                raise


def _is_unique_violation(e: Exception) -> bool:
    if isinstance(e, sqlite3.IntegrityError):
        return "UNIQUE" in str(e)
    return getattr(e, "sqlstate", None) == "23505"


# ---------- سازمان و کاربر ----------

def create_org_with_admin(org_name: str, username: str, display_name: str, password_hash: str,
                          slug: str | None = None) -> dict:
    if slug and get_org_by_slug(slug):
        raise DuplicateError("این آدرس سازمان قبلاً استفاده شده است.")
    try:
        with connect(transaction=True) as c:
            org_id = c.execute(
                "INSERT INTO organizations (name, slug) VALUES (?, ?) RETURNING id", (org_name, slug or None)
            ).fetchone()["id"]
            c.execute(
                "INSERT INTO users (org_id, username, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'admin')",
                (org_id, username, display_name, password_hash),
            )
    except Exception as e:
        if _is_unique_violation(e):
            raise DuplicateError("این نام کاربری قبلاً ثبت شده است.") from e
        raise
    return get_user_by_username(username)


def get_org_by_slug(slug: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id, name, slug FROM organizations WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def get_org(org_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id, name, slug FROM organizations WHERE id = ?", (org_id,)).fetchone()
    return dict(row) if row else None


def set_org_slug(org_id: int, slug: str) -> None:
    try:
        with connect() as c:
            c.execute("UPDATE organizations SET slug = ? WHERE id = ?", (slug, org_id))
    except Exception as e:
        if _is_unique_violation(e):
            raise DuplicateError("این آدرس سازمان قبلاً استفاده شده است.") from e
        raise


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
    try:
        with connect() as c:
            c.execute(
                "INSERT INTO users (org_id, username, display_name, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (org_id, username, display_name, password_hash, role),
            )
    except Exception as e:
        if _is_unique_violation(e):
            raise DuplicateError("این نام کاربری قبلاً ثبت شده است.") from e
        raise


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


ANSWER_MODES = ("sources", "sources_and_general")


def create_assistant(org_id: int, name: str, description: str, system_prompt: str,
                     answer_mode: str = "sources", starter_questions: str = "") -> int:
    with connect() as c:
        return c.execute(
            """INSERT INTO assistants (org_id, name, description, system_prompt, answer_mode, starter_questions)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (org_id, name, description, system_prompt, answer_mode, starter_questions),
        ).fetchone()["id"]


def update_assistant(org_id: int, assistant_id: int, name: str, description: str, system_prompt: str,
                     answer_mode: str = "sources", starter_questions: str = "") -> None:
    with connect() as c:
        c.execute(
            """UPDATE assistants SET name = ?, description = ?, system_prompt = ?, answer_mode = ?,
                      starter_questions = ?
               WHERE org_id = ? AND id = ?""",
            (name, description, system_prompt, answer_mode, starter_questions, org_id, assistant_id),
        )


def set_public_link(org_id: int, assistant_id: int, token: str | None, daily_limit: int | None = None) -> None:
    """token=None لینک عمومی را خاموش می‌کند؛ توکن تازه لینک قبلی را باطل می‌کند."""
    with connect() as c:
        if daily_limit is None:
            c.execute("UPDATE assistants SET public_token = ? WHERE org_id = ? AND id = ?",
                      (token, org_id, assistant_id))
        else:
            c.execute("UPDATE assistants SET public_token = ?, public_daily_limit = ? WHERE org_id = ? AND id = ?",
                      (token, daily_limit, org_id, assistant_id))


def get_public_assistant(token: str) -> dict | None:
    """دستیار متعلق به یک لینک عمومی فعال (با نام سازمان)."""
    if not token:
        return None
    with connect() as c:
        row = c.execute(
            """SELECT a.*, o.name AS org_name,
                      (SELECT COUNT(*) FROM chunks ch WHERE ch.assistant_id = a.id) AS n_chunks
               FROM assistants a JOIN organizations o ON o.id = a.org_id
               WHERE a.public_token = ?""",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def count_public_question(assistant_id: int, day: str) -> int:
    """یک سؤال عمومی امروز را ثبت می‌کند و تعداد کل سؤال‌های امروز را برمی‌گرداند (اتمی)."""
    with connect() as c:
        return c.execute(
            """INSERT INTO public_usage (assistant_id, day, n) VALUES (?, ?, 1)
               ON CONFLICT (assistant_id, day) DO UPDATE SET n = public_usage.n + 1
               RETURNING n""",
            (assistant_id, day),
        ).fetchone()["n"]


def public_usage_today(assistant_id: int, day: str) -> int:
    with connect() as c:
        row = c.execute("SELECT n FROM public_usage WHERE assistant_id = ? AND day = ?", (assistant_id, day)).fetchone()
    return row["n"] if row else 0


def delete_assistant(org_id: int, assistant_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM assistants WHERE org_id = ? AND id = ?", (org_id, assistant_id))


# ---------- منابع و تکه‌ها ----------

def create_source(org_id: int, assistant_id: int, kind: str, name: str, embed_model: str) -> int:
    with connect() as c:
        return c.execute(
            "INSERT INTO sources (org_id, assistant_id, kind, name, embed_model) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (org_id, assistant_id, kind, name, embed_model),
        ).fetchone()["id"]


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
    with connect(transaction=True) as c:
        # تکه‌های قبلی همین منبع پاک می‌شوند تا تلاش دوباره (بعد از قطع اتصال) تکراری نسازد
        c.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        if c.pg:
            c.executemany(
                """INSERT INTO chunks (org_id, assistant_id, source_id, idx, location, content, search_text, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (org_id, assistant_id, source_id, i, loc, text, " ".join(tokenize(text)), emb[i])
                    for i, (loc, text) in enumerate(items)
                ],
            )
        else:
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
        return c.execute("SELECT COUNT(*) AS n FROM chunks WHERE org_id = ?", (org_id,)).fetchone()["n"]


# ---------- جستجو ----------

_CHUNK_COLUMNS = "ch.id, ch.source_id, ch.location, ch.content, s.name AS source_name"


def hybrid_search(org_id: int, assistant_id: int, query_vec: np.ndarray,
                  tokens: list[str], limit: int) -> tuple[list[dict], list[dict]]:
    """فقط Postgres: جستجوی معنایی (pgvector) و تمام‌متن در یک رفت‌وبرگشت.
    دو فهرست رتبه‌بندی‌شده برمی‌گرداند: (بر اساس بردار، بر اساس کلیدواژه)."""
    scope = "ch.org_id = ? AND ch.assistant_id = ? AND s.status = 'ready'"
    vec = np.asarray(query_vec, dtype=np.float32)
    params: list = [vec, org_id, assistant_id, vec, limit]
    if tokens:
        # توکن‌ها فقط حروف/عدد هستند (\w+)؛ هر توکن سؤال کافی است (OR)
        keyword_cte = f"""SELECT ch.id, row_number() OVER (ORDER BY ts_rank_cd(ch.tsv, q) DESC) AS r
                FROM chunks ch JOIN sources s ON s.id = ch.source_id, to_tsquery('simple', ?) AS q
                WHERE {scope} AND ch.tsv @@ q
                ORDER BY ts_rank_cd(ch.tsv, q) DESC LIMIT ?"""
        params += [" | ".join(f"'{t}'" for t in dict.fromkeys(tokens)), org_id, assistant_id, limit]
    else:
        keyword_cte = "SELECT NULL::bigint AS id, NULL::bigint AS r WHERE false"
    with connect() as c:
        rows = _rows(c.execute(
            f"""WITH v AS (
                    SELECT ch.id, row_number() OVER (ORDER BY ch.embedding <=> ?) AS r
                    FROM chunks ch JOIN sources s ON s.id = ch.source_id
                    WHERE {scope}
                    ORDER BY ch.embedding <=> ? LIMIT ?
                ), k AS ({keyword_cte})
                SELECT {_CHUNK_COLUMNS}, v.r AS v_rank, k.r AS k_rank
                FROM chunks ch JOIN sources s ON s.id = ch.source_id
                LEFT JOIN v ON v.id = ch.id LEFT JOIN k ON k.id = ch.id
                WHERE v.id IS NOT NULL OR k.id IS NOT NULL""",
            params,
        ))
    by_vector = sorted((r for r in rows if r["v_rank"] is not None), key=lambda r: r["v_rank"])
    by_keyword = sorted((r for r in rows if r["k_rank"] is not None), key=lambda r: r["k_rank"])
    return by_vector, by_keyword


def chunks_signature(org_id: int, assistant_id: int) -> tuple:
    """فقط SQLite: برای تشخیص تغییر پایگاه دانش (و باطل کردن کش جستجوی درون‌حافظه)."""
    with connect() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id, COALESCE(SUM(id), 0) AS sum_id
               FROM chunks WHERE org_id = ? AND assistant_id = ?""",
            (org_id, assistant_id),
        ).fetchone()
    return row["n"], row["max_id"], row["sum_id"]


def load_chunks(org_id: int, assistant_id: int) -> list[dict]:
    """فقط SQLite: همه‌ی تکه‌ها با بردارشان برای جستجوی درون‌حافظه."""
    with connect() as c:
        rows = c.execute(
            f"""SELECT {_CHUNK_COLUMNS}, ch.embedding
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
