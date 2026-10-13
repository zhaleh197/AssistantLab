import streamlit as st

from core import chat_ui, db, perf
from core.ui import current_user, pick_assistant

user = current_user()
org_id = user["org_id"]

with perf.timed("list_assistants"):
    assistants = db.list_assistants(org_id)
if not assistants:
    st.title("گفتگو")
    if user["role"] == "admin":
        st.info("هنوز دستیاری ندارید. از صفحه‌ی «دستیارها» یکی بسازید.")
    else:
        st.info("مدیر سازمان هنوز دستیاری نساخته است.")
    st.stop()

with st.sidebar:
    assistant = pick_assistant(assistants, key="chat_assistant")

st.title(assistant["name"])
if assistant["description"]:
    st.caption(assistant["description"])

chats = st.session_state.setdefault("chats", {})
history: list[dict] = chats.setdefault(assistant["id"], [])

with st.sidebar:
    if st.button("گفتگوی جدید", icon=":material/add_comment:", disabled=not history):
        history.clear()
        st.rerun()

chat_ui.render_history(history, show_excerpts=True)

if not history and assistant["n_chunks"] == 0:
    st.info("این دستیار هنوز منبعی ندارد؛ تا منبع اضافه نشود نمی‌تواند پاسخ دقیق بدهد.")

question = st.chat_input("سؤال خود را بپرسید...")
if question:
    chat_ui.answer(assistant, history, question, show_excerpts=True)
