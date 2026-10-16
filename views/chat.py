import streamlit as st

from core import chat_ui, db, perf
from core.ui import current_user, pick_assistant

st.set_page_config(layout="centered")  # گفتگو در ستون باریک‌تر خواناتر است

user = current_user()
org_id = user["org_id"]

with perf.timed("list_assistants"):
    assistants = db.list_assistants(org_id)
if not assistants:
    st.title("گفتگو", icon=":material/chat:")
    if user["role"] == "admin":
        st.info("هنوز دستیاری ندارید. از صفحه‌ی «دستیارها» یکی بسازید.", icon=":material/smart_toy:")
    else:
        st.info("مدیر سازمان هنوز دستیاری نساخته است.", icon=":material/hourglass_empty:")
    st.stop()

with st.sidebar:
    assistant = pick_assistant(assistants, key="chat_assistant")

chats = st.session_state.setdefault("chats", {})
history: list[dict] = chats.setdefault(assistant["id"], [])
pills_key = f"starters_{assistant['id']}"

with st.sidebar:
    if st.button("گفتگوی جدید", icon=":material/add_comment:", disabled=not history, width="stretch"):
        history.clear()
        st.rerun()

# کادر پیام همیشه پایین صفحه است؛ زودتر خوانده می‌شود تا با اولین سؤال صفحه‌ی خوش‌آمد کنار برود
typed = st.chat_input("سؤال خود را بپرسید...", submit_mode="disable")
question = typed or chat_ui.take_starter(pills_key)

if history or question:
    st.subheader(assistant["name"], icon=":material/smart_toy:")
else:
    chat_ui.welcome(assistant, pills_key)
    if assistant["n_chunks"] == 0:
        st.container(key="center_no_sources").caption("\u200f:material/info: این دستیار هنوز منبعی ندارد؛ تا منبع اضافه نشود نمی‌تواند پاسخ دقیق بدهد.",
                   text_alignment="center")

chat_ui.render_history(history, show_excerpts=True)

if question:
    chat_ui.answer(assistant, history, question, show_excerpts=True)
