import html
import sys
import time

import streamlit as st
from openai import APIError, NotFoundError

from core import db, llm, perf, rag, retrieval
from core.ui import current_user, pick_assistant
import config

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


def render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"📚 منابع ({len(sources)})"):
        for s in sources:
            st.markdown(f"**[{s['n']}] {html.escape(s['label'])}**")
            st.markdown(f"<div class='source-box'>{html.escape(s['content'])}</div>", unsafe_allow_html=True)


for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_sources(msg.get("sources", []))

if not history and assistant["n_chunks"] == 0:
    st.info("این دستیار هنوز منبعی ندارد؛ تا منبع اضافه نشود نمی‌تواند پاسخ دقیق بدهد.")

question = st.chat_input("سؤال خود را بپرسید...")
if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            if rag.is_small_talk(question):
                hits = []  # احوال‌پرسی و تشکر جستجو نمی‌خواهد
            else:
                with st.spinner("در حال جستجو در منابع..."):
                    hits = retrieval.search(
                        org_id, assistant["id"], rag.retrieval_query(history, question), config.TOP_K
                    )
            messages = rag.build_messages(assistant, history, question, hits)
            started = time.perf_counter()
            waiting = st.empty()
            waiting.caption("در حال نوشتن پاسخ...")

            def timed_stream():
                first = True
                for piece in llm.stream_chat(messages):
                    if first:
                        waiting.empty()
                        perf.log("llm first token", (time.perf_counter() - started) * 1000)
                        first = False
                    yield piece

            answer = st.write_stream(timed_stream())
            waiting.empty()
            perf.log("llm full answer", (time.perf_counter() - started) * 1000)
        except llm.MissingApiKey as e:
            st.error(str(e))
            st.stop()
        except NotFoundError:
            print(f"chat model not found: {config.CHAT_MODEL}", file=sys.stderr)
            st.error("مدل زبانی تنظیم‌شده در دسترس نیست؛ به مدیر سیستم اطلاع دهید.")
            st.stop()
        except llm.TRANSIENT_ERRORS:
            st.warning("سرویس مدل زبانی الان شلوغ است؛ چند لحظه بعد دوباره بپرسید.")
            st.stop()
        except APIError as e:
            print(f"chat API error: {e}", file=sys.stderr)
            st.error("خطا در ارتباط با مدل زبانی؛ دوباره امتحان کنید.")
            st.stop()

        if not answer or not answer.strip():
            st.warning("پاسخی دریافت نشد؛ لطفاً دوباره بپرسید.")
            st.stop()

        cited = rag.cited_numbers(answer, len(hits))
        sources = [
            {"n": n, "label": rag.format_hit_label(hits[n - 1]), "content": hits[n - 1].content}
            for n in cited
        ]
        render_sources(sources)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer, "sources": sources})
