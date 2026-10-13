"""نگه‌داری توکن نشست ورود در localStorage مرورگر.

پراکسی Streamlit Community Cloud کوکی‌ها را به برنامه نمی‌رساند، پس ورود ماندگار با کوکی آنجا
کار نمی‌کند. به‌جای آن توکن در حافظه‌ی مرورگر نگه داشته می‌شود و این کامپوننت کوچک
(که داخل خود صفحه اجرا می‌شود، نه در iframe) آن را به سرور گزارش می‌کند.
"""
import streamlit as st

_KEY = "_al_browser_store"
_PENDING = "_al_browser_store_pending"

_COMPONENT = st.components.v2.component(
    "assistantlab_session_store",
    html="<span></span>",
    js="""
export default function (component) {
  const { data, setStateValue } = component
  const STORAGE_KEY = "assistantlab.session"
  let stored = ""
  try {
    if (data?.action === "save" && data?.token) {
      window.localStorage.setItem(STORAGE_KEY, data.token)
    } else if (data?.action === "clear") {
      window.localStorage.removeItem(STORAGE_KEY)
    }
    stored = window.localStorage.getItem(STORAGE_KEY) || ""
  } catch (e) {
    stored = ""
  }
  // فقط وقتی با مقداری که سرور می‌داند فرق دارد گزارش می‌شود تا اجرای دوباره‌ی بی‌پایان رخ ندهد
  if (stored !== data?.known) {
    setStateValue("token", stored)
  }
}
""",
)


def sync() -> str | None:
    """توکن ذخیره‌شده در مرورگر را برمی‌گرداند.

    None: مرورگر هنوز گزارش نداده (فقط اولین اجرای هر نشست؛ گزارش خودش اجرای دوباره می‌سازد).
    "": توکنی ذخیره نشده است.
    باید در هر اجرا و قبل از هر چیز دیگری صدا زده شود.
    """
    pending = st.session_state.get(_PENDING)
    state = st.session_state.get(_KEY)
    known = state.get("token") if state else None
    action, token = pending or (None, None)

    result = _COMPONENT(
        key=_KEY,
        data={"action": action, "token": token, "known": known},
        on_token_change=lambda: None,
    )

    if pending:
        expected = token if action == "save" else ""
        if result.token == expected:
            st.session_state.pop(_PENDING, None)
        # تا مرورگر تأیید کند، مقدار مورد انتظار برگردانده می‌شود
        return expected
    return result.token


def save(token: str) -> None:
    st.session_state[_PENDING] = ("save", token)


def clear() -> None:
    st.session_state[_PENDING] = ("clear", None)
