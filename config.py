"""تنظیمات برنامه؛ از فایل .env یا متغیرهای محیطی (Secrets در Hugging Face) خوانده می‌شود."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


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

# مدل گفتگو (هر سرویس سازگار با OpenAI: Gemini، Groq، OpenRouter، ...)
CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", GEMINI_OPENAI_URL)
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.8-flash")

# مدل Embedding (اگر کلید جدا داده نشود، از کلید گفتگو استفاده می‌شود)
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", GEMINI_OPENAI_URL)
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "") or CHAT_API_KEY
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
MAX_URL_BYTES = 20 * 1024 * 1024
# اگر متن HTML خام کمتر از این باشد، صفحه احتمالاً با جاوااسکریپت ساخته می‌شود و با مرورگر رندر می‌شود
MIN_STATIC_TEXT_CHARS = int(os.getenv("MIN_STATIC_TEXT_CHARS", 300))
RENDER_TIMEOUT_MS = 30_000
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", 50))
