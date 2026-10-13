"""تنظیمات برنامه؛ از فایل .env، متغیرهای محیطی یا Secrets در Streamlit Cloud خوانده می‌شود."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def _load_streamlit_secrets() -> None:
    """Streamlit Cloud مقدارهای Secrets را فقط وقتی st.secrets خوانده شود در اختیار می‌گذارد؛
    کلیدهای سطح اول به متغیرهای محیطی منتقل می‌شوند تا بقیه‌ی تنظیمات مثل .env کار کنند."""
    try:
        import streamlit as st

        items = dict(st.secrets)
    except Exception:  # بدون فایل secrets (اجرای محلی با .env)
        return
    for key, value in items.items():
        if isinstance(value, (str, int, float, bool)):
            os.environ.setdefault(key, str(value))


_load_streamlit_secrets()


def _fix_ssl_env() -> None:
    """اگر SSL_CERT_FILE به فایلی غیر از گواهی اشاره کند، HTTPS در پایتون از کار می‌افتد.
    در این حالت فقط برای همین پروسه نادیده‌اش می‌گیریم."""
    path = os.environ.get("SSL_CERT_FILE")
    if not path:
        return
    try:
        with open(path, "rb") as f:
            looks_like_cert = b"BEGIN CERTIFICATE" in f.read()
    except OSError:
        looks_like_cert = False
    if not looks_like_cert:
        os.environ.pop("SSL_CERT_FILE", None)


_fix_ssl_env()

# اگر مرورگر Playwright داخل پوشه‌ی پروژه نصب شده باشد (به‌جای درایو C)، از همان استفاده شود
if (ROOT / ".playwright").is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright"))

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# سرویس‌های مدل زبانی (همه سازگار با OpenAI)؛ کلید هر سرویس جداگانه تنظیم می‌شود
PROVIDER_URLS = {
    "gemini": GEMINI_OPENAI_URL,
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
# CHAT_API_KEY نام قدیمی کلید Gemini است و هنوز پذیرفته می‌شود
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("CHAT_API_KEY", "")
PROVIDER_KEYS = {
    "gemini": GEMINI_API_KEY,
    "groq": os.getenv("GROQ_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
}

# مدل‌های گفتگو به ترتیب اولویت («سرویس:مدل»)؛ اگر یکی خطا بدهد یا دیر شروع کند، بعدی امتحان می‌شود
# و مدلی که کلید سرویسش تنظیم نشده نادیده گرفته می‌شود. در سنجش‌ها Groq زیر ۱ ثانیه جواب می‌داد و
# Gemini رایگان ۵ ثانیه تا یک دقیقه (یا خطای 503)، پس Gemini آخرین پشتیبان است.
CHAT_MODELS = os.getenv(
    "CHAT_MODELS", "groq:qwen/qwen3.8-27b, groq:openai/gpt-oss-120b, gemini:gemini-3.5-flash"
)
# میزان «فکر کردن» مدل‌های Gemini قبل از پاسخ (minimal/low/medium/high)؛ خالی = پیش‌فرض مدل
GEMINI_REASONING_EFFORT = os.getenv("GEMINI_REASONING_EFFORT", "minimal")
# اگر مدل اصلی در این چند ثانیه شروع به پاسخ نکند، مدل جایگزین امتحان می‌شود
CHAT_FIRST_TOKEN_TIMEOUT = float(os.getenv("CHAT_FIRST_TOKEN_TIMEOUT", 8))
CHAT_LAST_MODEL_TIMEOUT = float(os.getenv("CHAT_LAST_MODEL_TIMEOUT", 30))

# مدل Embedding (پیش‌فرض Gemini با همان کلید Gemini)
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", GEMINI_OPENAI_URL)
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "") or GEMINI_API_KEY
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")

# ابعاد بردار Embedding (۷۶۸ یک‌چهارم حجم ۳۰۷۲ است). صفر = پیش‌فرض خود مدل.
# بعد از افزودن منابع عوضش نکنید؛ ستون بردار در Postgres همین ابعاد را دارد.
EMBED_DIMENSIONS = int(os.getenv("EMBED_DIMENSIONS", 768))

# ذخیره‌سازی: اگر DATABASE_URL (مثلاً Session pooler سوپابیس) تنظیم شود Postgres، وگرنه SQLite محلی
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_SCHEMA = os.getenv("DB_SCHEMA", "assistantlab")
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "assistantlab.db"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))
TOP_K = int(os.getenv("TOP_K", 6))
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", 6))

# سهمیه‌ی هر سازمان
MAX_CHUNKS_PER_ORG = int(os.getenv("MAX_CHUNKS_PER_ORG", 5000))
# لینک عمومی دستیارها: حداکثر سؤال در یک گفتگوی بازدیدکننده (سقف روزانه را مدیر هر دستیار تعیین می‌کند)
PUBLIC_SESSION_LIMIT = int(os.getenv("PUBLIC_SESSION_LIMIT", 30))
# آدرس پایه‌ی برنامه برای ساخت لینک‌ها؛ خالی = از آدرس فعلی مرورگر
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

MAX_URL_BYTES = 20 * 1024 * 1024
# اگر متن HTML خام کمتر از این باشد، صفحه احتمالاً با جاوااسکریپت ساخته می‌شود و با مرورگر رندر می‌شود
MIN_STATIC_TEXT_CHARS = int(os.getenv("MIN_STATIC_TEXT_CHARS", 300))
RENDER_TIMEOUT_MS = 30_000
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", 50))
