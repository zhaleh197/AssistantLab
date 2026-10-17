"""نمایش گفتگو و تولید پاسخ؛ مشترک بین صفحه‌ی گفتگوی کارکنان و لینک عمومی دستیار."""
import html
import re
import sys
import time

import streamlit as st
from openai import APIError, NotFoundError

import config
from core import chat_style, llm, perf, rag, retrieval

USER_AVATAR = ":material/person:"


def _avatar(assistant: dict) -> str:
    """آواتار دستیار؛ صفحه‌ها آن را از تنظیمات برند سازمان در assistant["avatar"] می‌گذارند."""
    return assistant.get("avatar") or chat_style.assistant_avatar(None, assistant["name"])
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~<])")


def md_escape(text: str) -> str:
    """متن‌هایی که از کاربر یا اسناد می‌آیند نباید به‌عنوان Markdown (لینک، تصویر، ...) تفسیر شوند."""
    return _MD_SPECIAL.sub(r"\\\1", text)


def starter_questions(assistant: dict) -> list[str]:
    lines = (assistant.get("starter_questions") or "").splitlines()
    return [q.strip() for q in lines if q.strip()][:6]


# ---------- صفحه‌ی خوش‌آمد ----------

def welcome(assistant: dict, pills_key: str) -> None:
    """پیش از اولین پیام: معرفی گرم دستیار و کارت‌های سؤال پیشنهادی."""
    st.html(chat_style.hero_html(assistant["name"], assistant.get("description") or "", _avatar(assistant)))
    questions = starter_questions(assistant)
    if not questions:
        return
    st.html('<p class="al-suggest-title">می‌توانید از این‌جا شروع کنید</p>')
    with st.container(key="al_suggest"):
        # ردیف به ردیف (نه ستون به ستون) تا در گوشی که ستون‌ها زیر هم می‌روند، ترتیب سؤال‌ها حفظ شود
        for row in range(0, len(questions), 2):
            columns = st.columns(2)
            for col, (i, q) in zip(columns, enumerate(questions[row:row + 2], start=row)):
                col.button(
                    q, key=f"{pills_key}_{i}", icon=":material/chat_bubble:", width="stretch",
                    on_click=_pick_starter, args=(pills_key, q),
                )


def _pick_starter(pills_key: str, question: str) -> None:
    st.session_state[f"{pills_key}_pending"] = question


def take_starter(pills_key: str) -> str | None:
    """سؤال پیشنهادی‌ای که کاربر رویش کلیک کرده (یک بار)."""
    return st.session_state.pop(f"{pills_key}_pending", None)


def header(assistant: dict, on_new_chat=None) -> None:
    """سرصفحه‌ی چسبان در طول گفتگو: آواتار، نام، وضعیت و دکمه‌ی گفتگوی جدید."""
    with st.container(key="al_header", horizontal=True, vertical_alignment="center"):
        st.html(chat_style.header_html(assistant["name"], _avatar(assistant)), width="stretch")
        if on_new_chat and st.button("گفتگوی جدید", icon=":material/add_comment:", type="tertiary"):
            on_new_chat()


# ---------- پیام‌ها و منابع ----------

def render_sources(sources: list[dict], show_excerpts: bool) -> None:
    """کارکنان: متن هر منبع. لینک عمومی: فقط نام اسناد (بدون تکرار) و بدون متن داخلی آن‌ها."""
    if not sources:
        return
    names = list(dict.fromkeys(s.get("source_name") or s["label"] for s in sources))
    st.html(chat_style.sources_html(names))
    if not show_excerpts:
        return
    with st.expander(f"متن منابع ({len(sources)})", icon=":material/menu_book:"):
        for s in sources:
            st.markdown(f"**[{s['n']}] {html.escape(s['label'])}**")
            st.markdown(f"<div class='source-box'>{html.escape(s['content'])}</div>", unsafe_allow_html=True)


def render_history(assistant: dict, history: list[dict], show_excerpts: bool) -> None:
    for msg in history:
        with st.chat_message(msg["role"], avatar=USER_AVATAR if msg["role"] == "user" else _avatar(assistant)):
            st.markdown(msg["content"])
            render_sources(msg.get("sources", []), show_excerpts)


def answer(assistant: dict, history: list[dict], question: str, show_excerpts: bool) -> None:
    """سؤال را نمایش می‌دهد، پاسخ را جریانی می‌نویسد و هر دو را به history اضافه می‌کند.
    در صورت خطا پیام مناسب نمایش داده می‌شود و اجرای صفحه متوقف می‌شود."""
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    with st.chat_message("assistant", avatar=_avatar(assistant)):
        try:
            if rag.is_small_talk(question):
                hits = []  # احوال‌پرسی و تشکر جستجو نمی‌خواهد
            else:
                with st.status(":shimmer[در حال جستجو در منابع...]", type="compact") as status:
                    hits = retrieval.search(
                        assistant["org_id"], assistant["id"], rag.retrieval_query(history, question), config.TOP_K
                    )
                    status.update(label=f"{len(hits)} بخش مرتبط در منابع پیدا شد", state="complete")
            messages = rag.build_messages(assistant, history, question, hits)
            started = time.perf_counter()
            waiting = st.empty()
            waiting.html(chat_style.TYPING_HTML)

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
            st.error("دستیار هنوز به‌درستی تنظیم نشده است؛ به مدیر سیستم اطلاع دهید.", icon=":material/error:")
            st.stop()
        except NotFoundError:
            print(f"no chat model found among: {config.CHAT_MODELS}", file=sys.stderr)
            st.error("مدل زبانی تنظیم‌شده در دسترس نیست؛ به مدیر سیستم اطلاع دهید.", icon=":material/error:")
            st.stop()
        except llm.TRANSIENT_ERRORS:
            st.warning("سرویس الان شلوغ است؛ چند لحظه بعد دوباره بپرسید.", icon=":material/schedule:")
            st.stop()
        except APIError as e:
            print(f"chat API error: {e}", file=sys.stderr)
            st.error("خطا در ارتباط با مدل زبانی؛ دوباره امتحان کنید.", icon=":material/error:")
            st.stop()

        if not text or not text.strip():
            st.warning("پاسخی دریافت نشد؛ لطفاً دوباره بپرسید.", icon=":material/refresh:")
            st.stop()

        sources = [
            {"n": n, "label": rag.format_hit_label(hits[n - 1]), "source_name": hits[n - 1].source_name,
             "content": hits[n - 1].content}
            for n in rag.cited_numbers(text, len(hits))
        ]
        render_sources(sources, show_excerpts)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": text, "sources": sources})
