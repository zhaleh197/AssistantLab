"""هش و بررسی رمز عبور (PBKDF2-SHA256، بدون وابستگی خارجی)."""
import hashlib
import hmac
import re
import secrets

ITERATIONS = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def validate_new_account(username: str, password: str) -> str | None:
    """پیام خطا برمی‌گرداند، یا None اگر مشکلی نباشد."""
    if not USERNAME_RE.match(username):
        return "نام کاربری باید ۳ تا ۳۲ کاراکتر و فقط شامل حروف انگلیسی، عدد، _ . - باشد."
    if len(password) < 8:
        return "رمز عبور باید حداقل ۸ کاراکتر باشد."
    return None


def validate_slug(slug: str) -> str | None:
    if not SLUG_RE.match(slug):
        return "آدرس سازمان باید ۳ تا ۳۰ کاراکتر و فقط شامل حروف کوچک انگلیسی، عدد و - باشد (مثلاً akam)."
    return None
