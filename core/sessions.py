"""نشست‌های ماندگار ورود.

جریان ورود:
  ۱. بعد از بررسی رمز، یک «بلیت» یک‌بارمصرف و کوتاه‌عمر ساخته می‌شود.
  ۲. مرورگر به /auth/finish?ticket=... می‌رود؛ آن مسیر بلیت را با یک توکن نشست عوض می‌کند
     و توکن را در کوکی HttpOnly می‌گذارد (Streamlit خودش نمی‌تواند کوکی تنظیم کند).
  ۳. در هر اجرا، کاربر از روی کوکی شناسایی می‌شود.
در دیتابیس فقط هش توکن‌ها ذخیره می‌شود.
"""
import hashlib
import secrets
import time

from core import db

COOKIE_NAME = "al_session"
SESSION_TTL = 30 * 24 * 3600
TICKET_TTL = 60


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create(user_id: int, kind: str, ttl: int) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as c:
        c.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (time.time(),))
        c.execute(
            "INSERT INTO auth_tokens (token_hash, user_id, kind, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), user_id, kind, time.time() + ttl),
        )
    return token


def create_ticket(user_id: int) -> str:
    return _create(user_id, "ticket", TICKET_TTL)


def exchange_ticket(ticket: str) -> str | None:
    """بلیت را مصرف می‌کند و توکن نشست برمی‌گرداند (یا None اگر نامعتبر/منقضی باشد)."""
    if not ticket:
        return None
    with db.connect() as c:
        row = c.execute(
            "DELETE FROM auth_tokens WHERE token_hash = ? AND kind = 'ticket' RETURNING user_id, expires_at",
            (_hash(ticket),),
        ).fetchone()
    if not row or row["expires_at"] < time.time():
        return None
    return _create(row["user_id"], "session", SESSION_TTL)


def user_for_session(token: str | None) -> dict | None:
    if not token:
        return None
    with db.connect() as c:
        row = c.execute(
            """SELECT u.id, u.org_id, u.username, u.display_name, u.role, o.name AS org_name
               FROM auth_tokens t
               JOIN users u ON u.id = t.user_id
               JOIN organizations o ON o.id = u.org_id
               WHERE t.token_hash = ? AND t.kind = 'session' AND t.expires_at > ?""",
            (_hash(token), time.time()),
        ).fetchone()
    return dict(row) if row else None


def revoke(token: str | None) -> None:
    if token:
        with db.connect() as c:
            c.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (_hash(token),))


def revoke_all_for_user(user_id: int) -> None:
    with db.connect() as c:
        c.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
