"""ابزارهای مشترک رابط کاربری Streamlit."""
import time
from datetime import datetime
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import streamlit as st

import config

# Streamlit راست‌به‌چپ ندارد؛ فونت و رنگ‌ها از تم (.streamlit/config.toml) می‌آیند و اینجا فقط جهت متن است.
RTL_CSS = """
<style>
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stBottom"] { direction: rtl; }
input, textarea { direction: rtl; }
/* تراز پیش‌فرض Streamlit «چپ» است که برای فارسی غلط است؛ start یعنی راست برای فارسی و چپ برای انگلیسی */
[data-testid="stMarkdownContainer"] :is(p, li, h1, h2, h3, h4, h5, h6),
[data-testid="stCaptionContainer"] p, [data-testid="stHeading"] :is(h1, h2, h3, h4, h5, h6) {
    text-align: start !important;  /* استایل‌های خود Streamlit بعد از این بارگذاری می‌شوند */
}
/* عناصری که عمداً وسط‌چین‌اند داخل ظرفی با کلید center_... قرار می‌گیرند (کلاس پایدار st-key-...) */
[class*="st-key-center"] :is(p, li, h1, h2, h3, h4, h5, h6) { text-align: center !important; }
code, pre, [data-testid="stCode"] { direction: ltr; text-align: left; }
.source-box { border-right: 3px solid rgba(99, 102, 241, .6); padding: .4rem .8rem; margin: .4rem 0;
              background: rgba(99, 102, 241, .06); border-radius: .5rem; font-size: .9rem; white-space: pre-wrap; }
</style>
"""


def app_base_url() -> str:
    """آدرس پایه‌ی برنامه برای ساخت لینک‌های قابل اشتراک. در Streamlit Cloud برنامه زیر /~/+/
    داخل iframe اجرا می‌شود ولی لینک باید به آدرس اصلی اشاره کند، پس فقط مبدأ (origin) برداشته می‌شود."""
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    parts = urlsplit(st.context.url or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""


def share_link(**params: str) -> str:
    return f"{app_base_url()}/?{urlencode(params)}"


BRAND_CACHE = "_org_brand"
BRAND_CACHE_SECONDS = 60


def org_brand(org_id: int) -> dict:
    """تنظیمات برند سازمان؛ تا یک دقیقه در همین نشست نگه داشته می‌شود تا هر پیام یک رفت‌وبرگشت کمتر داشته باشد."""
    from core import branding, db

    cached = st.session_state.get(BRAND_CACHE)
    if cached and cached["org_id"] == org_id and time.monotonic() - cached["at"] < BRAND_CACHE_SECONDS:
        return cached["brand"]
    brand = branding.from_org(db.get_org(org_id))
    st.session_state[BRAND_CACHE] = {"org_id": org_id, "brand": brand, "at": time.monotonic()}
    return brand


def format_time(value) -> str:
    """SQLite زمان محلی را به‌صورت متن برمی‌گرداند و Postgres به‌صورت datetime (UTC)؛
    دومی به منطقه‌ی زمانی مرورگر کاربر تبدیل می‌شود."""
    if isinstance(value, datetime):
        try:
            value = value.astimezone(ZoneInfo(st.context.timezone or "UTC"))
        except Exception:  # منطقه‌ی زمانی نامعلوم یا نبود پایگاه tzdata
            pass
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value or "")[:16]


def apply_style() -> None:
    st.markdown(RTL_CSS, unsafe_allow_html=True)


def current_user() -> dict:
    return st.session_state["user"]


def require_admin() -> dict:
    user = current_user()
    if user["role"] != "admin":
        st.error("این بخش فقط برای مدیر سازمان در دسترس است.")
        st.stop()
    return user


def pick_assistant(assistants: list[dict], key: str, label: str = "دستیار") -> dict | None:
    """انتخاب دستیار؛ انتخاب بین صفحه‌ها حفظ می‌شود."""
    if not assistants:
        return None
    ids = [a["id"] for a in assistants]
    remembered = st.session_state.get("selected_assistant")
    index = ids.index(remembered) if remembered in ids else 0
    chosen = st.selectbox(label, assistants, index=index, format_func=lambda a: a["name"], key=key)
    st.session_state["selected_assistant"] = chosen["id"]
    return chosen
