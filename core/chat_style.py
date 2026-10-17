"""ظاهر صفحه‌ی گفتگو: آواتار، حباب‌های پیام، نشانگر تایپ، کارت سؤال‌های پیشنهادی.

انتخاب‌گرها فقط از ویژگی‌های پایدار استفاده می‌کنند (data-testid، aria-label و کلاس st-key-... ظرف‌های کلیددار)
تا با به‌روزرسانی Streamlit نشکنند. رنگ‌ها بر اساس حالت روشن/تیره‌ی کاربر در پایتون انتخاب می‌شوند،
چون Streamlit رنگ‌های تم را به‌صورت متغیر CSS در صفحه نمی‌گذارد.
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from core import branding

PALETTES = {
    "light": {
        "bg": "#ffffff", "card": "#ffffff", "card-border": "#e8e9f3",
        "card-shadow": "0 6px 24px -14px rgba(30, 27, 75, .35)", "muted": "#6b7085", "text": "#1d2033",
        "header-bg": "rgba(255, 255, 255, .82)", "dot": "#a0a4bd", "suggest-hover": "#f7f7ff",
    },
    "dark": {
        "bg": "#0f1117", "card": "#171a26", "card-border": "#272b3d",
        "card-shadow": "0 6px 24px -14px rgba(0, 0, 0, .6)", "muted": "#9aa0b8", "text": "#e6e8f2",
        "header-bg": "rgba(15, 17, 23, .8)", "dot": "#6b7091", "suggest-hover": "#1d2132",
    },
}

_CSS = """
/* پس‌زمینه با درخشش ملایم بالای صفحه */
[data-testid="stAppViewContainer"] {
  background: radial-gradient(900px 380px at 50% -140px, var(--al-glow), transparent 70%), var(--al-bg);
}
[data-testid="stHeader"] { background: transparent; }

/* ---------- صفحه‌ی خوش‌آمد ---------- */
.al-hero { text-align: center; padding: 2.2rem 0 .6rem; animation: al-rise .6s ease-out both; }
.al-hero-avatar {
  width: 88px; height: 88px; margin: 0 auto 1.1rem; border-radius: 28px;
  box-shadow: 0 16px 40px -12px var(--al-shadow); animation: al-float 6s ease-in-out infinite;
}
.al-hero-avatar img { width: 100%; height: 100%; display: block; }
.al-greet { font-size: 1.85rem; font-weight: 700; color: var(--al-text); margin: 0 0 .35rem; line-height: 1.5; }
.al-sub { color: var(--al-muted); font-size: 1rem; margin: 0 auto .9rem; max-width: 34rem; line-height: 1.9; }
.al-status {
  display: inline-flex; align-items: center; gap: .45rem; font-size: .8rem; color: #059669;
  background: rgba(16, 185, 129, .1); padding: .2rem .75rem; border-radius: 999px;
}
.al-status::before {
  content: ""; width: .5rem; height: .5rem; border-radius: 50%; background: #10b981;
  animation: al-pulse 2s infinite;
}
.al-suggest-title { color: var(--al-muted); font-size: .85rem; text-align: center; margin: 1.6rem 0 .2rem; }

/* کارت‌های سؤال پیشنهادی (دکمه‌های داخل ظرف al_suggest) */
.st-key-al_suggest button {
  width: 100%; min-height: 3.4rem; justify-content: flex-start; text-align: start; border-radius: 16px;
  background: var(--al-card); border: 1px solid var(--al-card-border); box-shadow: var(--al-card-shadow);
  transition: transform .15s ease, border-color .15s ease, background .15s ease; padding: .7rem 1rem;
}
.st-key-al_suggest button:hover {
  transform: translateY(-2px); border-color: var(--al-hover-border); background: var(--al-suggest-hover);
}
.st-key-al_suggest button p { text-align: start !important; font-size: .92rem; }

/* ---------- سرصفحه‌ی گفتگو ---------- */
.st-key-al_header {
  position: sticky; top: 0; z-index: 20; padding: .55rem 0; margin-bottom: .4rem;
  background: var(--al-header-bg); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--al-card-border);
}
.al-head { display: flex; align-items: center; gap: .75rem; }
.al-head img { width: 42px; height: 42px; border-radius: 14px; box-shadow: 0 6px 18px -8px var(--al-shadow); }
.al-head-name { font-weight: 700; font-size: 1.05rem; color: var(--al-text); line-height: 1.4; }
.al-head-status { font-size: .78rem; color: #059669; display: flex; align-items: center; gap: .35rem; }
.al-head-status::before { content: ""; width: .45rem; height: .45rem; border-radius: 50%; background: #10b981; }

/* ---------- پیام‌ها ---------- */
[data-testid="stChatMessage"] { background: transparent !important; padding: .35rem 0; animation: al-rise .35s ease-out both; }
/* پیام کاربر: حباب رنگی در سمت مقابل، بدون آواتار */
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid^="stChatMessageAvatar"] { display: none; }
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] {
  /* در راست‌به‌چپ، حباب کاربر به سمت مقابلِ دستیار (چپ) می‌رود */
  margin-inline-start: auto !important; margin-inline-end: 0 !important; flex: 0 1 auto; width: auto;
  max-width: 80%; padding: .7rem 1.05rem;
  background: linear-gradient(135deg, var(--al-brand), var(--al-brand-2)); color: var(--al-on-brand);
  border-radius: 20px; border-end-end-radius: 6px; box-shadow: 0 10px 24px -14px var(--al-shadow);
}
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] * { color: var(--al-on-brand) !important; }
/* پاسخ دستیار: کارت نرم کنار آواتار */
[data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] {
  background: var(--al-card); border: 1px solid var(--al-card-border); box-shadow: var(--al-card-shadow);
  border-radius: 20px; border-start-start-radius: 6px; padding: .85rem 1.15rem;  /* گوشه‌ی تیز سمت آواتار */
}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] img { border-radius: 12px; }
[data-testid="stChatMessageContent"] p, [data-testid="stChatMessageContent"] li { line-height: 2; }

/* نشانگر تایپ */
.al-typing { display: inline-flex; gap: .3rem; padding: .35rem .1rem; }
.al-typing span { width: .45rem; height: .45rem; border-radius: 50%; background: var(--al-dot); animation: al-bounce 1.2s infinite ease-in-out; }
.al-typing span:nth-child(2) { animation-delay: .15s; }
.al-typing span:nth-child(3) { animation-delay: .3s; }

/* منابع به‌صورت برچسب */
.al-sources { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .4rem; }
.al-sources-label { font-size: .78rem; color: var(--al-muted); }
.al-chip {
  font-size: .78rem; padding: .15rem .7rem; border-radius: 999px; background: var(--al-chip-bg);
  color: var(--al-chip-text); border: 1px solid var(--al-chip-border); max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* کادر پیام */
[data-testid="stChatInput"] { border-radius: 22px; box-shadow: 0 12px 34px -16px rgba(30, 27, 75, .45); }
[data-testid="stBottom"] > div { background: transparent; }

.al-footnote { text-align: center; color: var(--al-muted); font-size: .75rem; margin-top: .8rem; }

@keyframes al-rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes al-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
@keyframes al-pulse { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, .5); } 70% { box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
@keyframes al-bounce { 0%, 80%, 100% { transform: translateY(0); opacity: .45; } 40% { transform: translateY(-5px); opacity: 1; } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""


def apply(brand: dict | None = None) -> None:
    """استایل گفتگو با رنگ‌های برند سازمان (brand از branding.from_org)."""
    dark = st.context.theme.type == "dark"
    colors = dict(PALETTES["dark" if dark else "light"])
    p = branding.palette((brand or {}).get("color", branding.DEFAULT_COLOR))
    colors.update({
        "brand": p["brand"], "brand-2": p["brand-2"], "on-brand": p["on-brand"],
        "shadow": p["shadow"], "hover-border": p["hover-border"], "chip-border": p["chip-border"],
        "glow": p["glow-dark"] if dark else p["glow"],
        "chip-bg": p["chip-bg-dark"] if dark else p["chip-bg"],
        "chip-text": p["chip-text-dark"] if dark else p["chip-text"],
    })
    variables = "; ".join(f"--al-{k}: {v}" for k, v in colors.items())
    st.html(f"<style>:root {{ {variables} }}\n{_CSS}</style>")


def assistant_avatar(brand: dict | None, assistant_name: str) -> str:
    brand = brand or branding.from_org(None)
    return branding.avatar_uri(brand["color"], brand["mode"], assistant_name, brand["image"])


def greeting() -> str:
    """سلام متناسب با ساعت محلی کاربر."""
    try:
        hour = datetime.now(ZoneInfo(st.context.timezone or "Asia/Tehran")).hour
    except Exception:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "صبح بخیر"
    if 12 <= hour < 17:
        return "روز بخیر"
    if 17 <= hour < 21:
        return "عصر بخیر"
    return "شب بخیر"


def hero_html(name: str, description: str, avatar: str) -> str:
    sub = html.escape(description) if description else "سؤالتان را بپرسید تا از روی منابع پاسخ بدهم."
    return f"""<div class="al-hero">
  <div class="al-hero-avatar"><img src="{avatar}" alt=""></div>
  <p class="al-greet">{greeting()}! من {html.escape(name)} هستم</p>
  <p class="al-sub">{sub}</p>
  <span class="al-status">آنلاین و آماده‌ی پاسخ‌گویی</span>
</div>"""


def header_html(name: str, avatar: str) -> str:
    return f"""<div class="al-head">
  <img src="{avatar}" alt="">
  <div><div class="al-head-name">{html.escape(name)}</div><div class="al-head-status">آنلاین</div></div>
</div>"""


TYPING_HTML = '<div class="al-typing" aria-label="در حال نوشتن"><span></span><span></span><span></span></div>'


def sources_html(names: list[str]) -> str:
    chips = "".join(f'<span class="al-chip" dir="auto" title="{html.escape(n)}">{html.escape(n)}</span>' for n in names)
    return f'<div class="al-sources"><span class="al-sources-label">منبع:</span>{chips}</div>'
