"""گفتگو با یک دستیار از طریق لینک عمومی (?a=...)، بدون ورود."""
from datetime import datetime, timezone

import streamlit as st

import config
from core import chat_ui, db

assistant = st.session_state["public_assistant"]

st.title(assistant["name"])
st.caption(assistant["description"] or f"دستیار هوشمند {assistant['org_name']}")

history: list[dict] = st.session_state.setdefault("public_history", [])
chat_ui.render_history(history, show_excerpts=False)

asked = len(history) // 2
session_full = asked >= config.PUBLIC_SESSION_LIMIT
if session_full:
    st.info("به سقف تعداد سؤال در این گفتگو رسیده‌اید. برای ادامه، کمی بعد صفحه را دوباره باز کنید.")

question = st.chat_input("سؤال خود را بپرسید...", disabled=session_full)
if question:
    # سقف روزانه از سهمیه‌ی سرویس‌های مدل زبانی محافظت می‌کند (همه‌ی بازدیدکنندگان یک دستیار با هم)
    today = datetime.now(timezone.utc).date().isoformat()
    if db.count_public_question(assistant["id"], today) > assistant["public_daily_limit"]:
        st.warning("ظرفیت پاسخ‌گویی این دستیار برای امروز تمام شده است؛ لطفاً فردا دوباره سر بزنید.")
        st.stop()
    chat_ui.answer(assistant, history, question, show_excerpts=False)

st.caption(f"پاسخ‌ها به‌صورت خودکار و بر اساس اسناد {assistant['org_name']} تولید می‌شوند و ممکن است خطا داشته باشند.")
