"""گفتگو با یک دستیار از طریق لینک عمومی (?a=...)، بدون ورود."""
from datetime import datetime, timezone

import streamlit as st

import config
from core import chat_ui, db

assistant = st.session_state["public_assistant"]
PILLS_KEY = "public_starters"

st.set_page_config(page_title=assistant["name"], page_icon=":material/smart_toy:", layout="centered")

history: list[dict] = st.session_state.setdefault("public_history", [])
session_full = len(history) // 2 >= config.PUBLIC_SESSION_LIMIT

# کادر پیام همیشه پایین صفحه است؛ زودتر خوانده می‌شود تا با اولین سؤال صفحه‌ی خوش‌آمد کنار برود
typed = st.chat_input("سؤال خود را بپرسید...", disabled=session_full, submit_mode="disable")
question = None if session_full else (typed or chat_ui.take_starter(PILLS_KEY))

if history or question:
    # سرصفحه‌ی جمع‌وجور در طول گفتگو
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(assistant["name"], icon=":material/smart_toy:", width="stretch")
        if history and st.button("گفتگوی جدید", icon=":material/add_comment:", type="tertiary"):
            history.clear()
            st.rerun()
else:
    chat_ui.welcome(assistant, PILLS_KEY)

chat_ui.render_history(history, show_excerpts=False)

if session_full:
    st.caption("\u200f:material/info: به سقف تعداد سؤال در این گفتگو رسیده‌اید؛ برای ادامه «گفتگوی جدید» را بزنید.")

if question:
    # سقف روزانه از سهمیه‌ی سرویس‌های مدل زبانی محافظت می‌کند (همه‌ی بازدیدکنندگان یک دستیار با هم)
    today = datetime.now(timezone.utc).date().isoformat()
    if db.count_public_question(assistant["id"], today) > assistant["public_daily_limit"]:
        st.warning("ظرفیت پاسخ‌گویی این دستیار برای امروز تمام شده است؛ لطفاً فردا دوباره سر بزنید.",
                   icon=":material/schedule:")
        st.stop()
    chat_ui.answer(assistant, history, question, show_excerpts=False)

st.container(key="center_footer").caption(
    f"پاسخ‌ها به‌صورت خودکار و بر اساس اسناد {chat_ui.md_escape(assistant['org_name'])} تولید می‌شوند "
    "و ممکن است خطا داشته باشند.",
    text_alignment="center",
)
