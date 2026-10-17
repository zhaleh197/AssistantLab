"""گفتگو با یک دستیار از طریق لینک عمومی (?a=...)، بدون ورود."""
import html
from datetime import datetime, timezone

import streamlit as st

import config
from core import branding, chat_style, chat_ui, db

assistant = st.session_state["public_assistant"]
PILLS_KEY = "public_starters"

brand = branding.from_org(assistant)  # ستون‌های برند سازمان همراه دستیار خوانده می‌شوند
avatar = chat_style.assistant_avatar(brand, assistant["name"])
assistant = {**assistant, "avatar": avatar}

st.set_page_config(page_title=assistant["name"], page_icon=avatar, layout="centered")
chat_style.apply(brand)

history: list[dict] = st.session_state.setdefault("public_history", [])
session_full = len(history) // 2 >= config.PUBLIC_SESSION_LIMIT

# کادر پیام همیشه پایین صفحه است؛ زودتر خوانده می‌شود تا با اولین سؤال صفحه‌ی خوش‌آمد کنار برود
typed = st.chat_input("پیامتان را بنویسید...", disabled=session_full, submit_mode="disable")
question = None if session_full else (typed or chat_ui.take_starter(PILLS_KEY))

if history or question:
    chat_ui.header(assistant, on_new_chat=(lambda: (history.clear(), st.rerun())) if history else None)
else:
    chat_ui.welcome(assistant, PILLS_KEY)

chat_ui.render_history(assistant, history, show_excerpts=False)

if session_full:
    st.caption("‏:material/info: به سقف تعداد سؤال در این گفتگو رسیده‌اید؛ برای ادامه «گفتگوی جدید» را بزنید.")

if question:
    # سقف روزانه از سهمیه‌ی سرویس‌های مدل زبانی محافظت می‌کند (همه‌ی بازدیدکنندگان یک دستیار با هم)
    today = datetime.now(timezone.utc).date().isoformat()
    if db.count_public_question(assistant["id"], today) > assistant["public_daily_limit"]:
        st.warning("ظرفیت پاسخ‌گویی این دستیار برای امروز تمام شده است؛ لطفاً فردا دوباره سر بزنید.",
                   icon=":material/schedule:")
        st.stop()
    chat_ui.answer(assistant, history, question, show_excerpts=False)

st.html(
    f'<p class="al-footnote">پاسخ‌ها به‌صورت خودکار و بر اساس اسناد {html.escape(assistant["org_name"])} '
    "تولید می‌شوند و ممکن است خطا داشته باشند.</p>"
)
