"""نمایش گفتگو و تولید پاسخ؛ مشترک بین صفحه‌ی گفتگوی کارکنان و لینک عمومی دستیار."""
import html
import sys
import time

import streamlit as st
from openai import APIError, NotFoundError

import config
from core import llm, perf, rag, retrieval


def render_sources(sources: list[dict], show_excerpts: bool) -> None:
    """show_excerpts=False (لینک عمومی): فقط نام منبع، بدون متن داخلی اسناد سازمان."""
    if not sources:
        return
    with st.expander(f"📚 منابع ({len(sources)})"):
        for s in sources:
            st.markdown(f"**[{s['n']}] {html.escape(s['label'])}**")
            if show_excerpts:
                st.markdown(f"<div class='source-box'>{html.escape(s['content'])}</div>", unsafe_allow_html=True)


def render_history(history: list[dict], show_excerpts: bool) -> None:
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            render_sources(msg.get("sources", []), show_excerpts)


def answer(assistant: dict, history: list[dict], question: str, show_excerpts: bool) -> None:
    """سؤال را نمایش می‌دهد، پاسخ را جریانی می‌نویسد و هر دو را به history اضافه می‌کند.
    در صورت خطا پیام مناسب نمایش داده می‌شود و اجرای صفحه متوقف می‌شود."""
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            if rag.is_small_talk(question):
                hits = []  # احوال‌پرسی و تشکر جستجو نمی‌خواهد
            else:
                with st.spinner("در حال جستجو در منابع..."):
                    hits = retrieval.search(
                        assistant["org_id"], assistant["id"], rag.retrieval_query(history, question), config.TOP_K
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

            text = st.write_stream(timed_stream())
            waiting.empty()
            perf.log("llm full answer", (time.perf_counter() - started) * 1000)
        except llm.MissingApiKey as e:
            print(f"chat config error: {e}", file=sys.stderr)
            st.error("دستیار هنوز به‌درستی تنظیم نشده است؛ به مدیر سیستم اطلاع دهید.")
            st.stop()
        except NotFoundError:
            print(f"no chat model found among: {config.CHAT_MODELS}", file=sys.stderr)
            st.error("مدل زبانی تنظیم‌شده در دسترس نیست؛ به مدیر سیستم اطلاع دهید.")
            st.stop()
        except llm.TRANSIENT_ERRORS:
            st.warning("سرویس مدل زبانی الان شلوغ است؛ چند لحظه بعد دوباره بپرسید.")
            st.stop()
        except APIError as e:
            print(f"chat API error: {e}", file=sys.stderr)
            st.error("خطا در ارتباط با مدل زبانی؛ دوباره امتحان کنید.")
            st.stop()

        if not text or not text.strip():
            st.warning("پاسخی دریافت نشد؛ لطفاً دوباره بپرسید.")
            st.stop()

        sources = [
            {"n": n, "label": rag.format_hit_label(hits[n - 1]), "content": hits[n - 1].content}
            for n in rag.cited_numbers(text, len(hits))
        ]
        render_sources(sources, show_excerpts)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": text, "sources": sources})
