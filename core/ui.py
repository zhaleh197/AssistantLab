"""ابزارهای مشترک رابط کاربری Streamlit."""
import streamlit as st

RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700&display=swap');

[data-testid="stAppViewContainer"], [data-testid="stSidebar"] { direction: rtl; }
[data-testid="stMarkdownContainer"], p, li, h1, h2, h3, h4, h5, h6, label,
input, textarea, button, [data-testid="stCaptionContainer"], [data-baseweb="select"],
[data-testid="stChatMessageContent"], [data-testid="stExpander"] summary {
    font-family: 'Vazirmatn', 'Source Sans Pro', sans-serif !important;
}
[data-testid="stMarkdownContainer"], [data-testid="stChatMessageContent"],
[data-testid="stCaptionContainer"] { text-align: right; }
input, textarea { direction: rtl; text-align: right; }
code, pre, [data-testid="stCode"] { direction: ltr; text-align: left; }
[data-testid="stSidebarNav"] a { flex-direction: row-reverse; justify-content: flex-end; gap: .5rem; }
.source-box { border-right: 3px solid #6c8cff; padding: .4rem .8rem; margin: .4rem 0;
              background: rgba(108,140,255,.07); border-radius: 4px; font-size: .9rem;
              white-space: pre-wrap; }
</style>
"""


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
