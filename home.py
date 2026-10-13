"""رابط کاربری اصلی (از طریق app.py اجرا می‌شود: streamlit run app.py)"""
import time

import streamlit as st

import config
from core import auth, browser_store, db, perf, sessions
from core.ui import apply_style

_run_started = time.perf_counter()

st.set_page_config(page_title="AssistantLab", page_icon="🤖", layout="wide")
apply_style()
try:
    with perf.timed("init_db"):
        db.init_db()
except Exception as e:  # تنظیمات اشتباه DATABASE_URL یا قطع اتصال
    st.error(f"اتصال به دیتابیس برقرار نشد: {e}")
    st.stop()

# توکن ورود در مرورگر نگه داشته می‌شود (core/browser_store.py)؛ در اولین اجرای هر نشست
# مرورگر هنوز آن را گزارش نکرده و گزارشش خودش یک اجرای دوباره می‌سازد
PAGES = {
    "chat": st.Page("views/chat.py", title="گفتگو", icon=":material/chat:", default=True),
    "assistants": st.Page("views/assistants.py", title="دستیارها", icon=":material/smart_toy:"),
    "sources": st.Page("views/sources.py", title="منابع", icon=":material/library_books:"),
    "team": st.Page("views/team.py", title="اعضای سازمان", icon=":material/group:"),
}

stored_token = browser_store.sync()
if stored_token is None:
    # همه‌ی صفحه‌ها (پنهان) ثبت می‌شوند تا آدرس صفحه‌ای که کاربر مستقیم باز کرده حفظ شود
    st.navigation(list(PAGES.values()), position="hidden")
    st.caption("در حال بارگذاری...")
    st.stop()

SESSION_RECHECK_SECONDS = 60
AUTH_CACHE = "_auth_cache"
DB_UNAVAILABLE = "ارتباط با دیتابیس برقرار نشد؛ چند لحظه بعد دوباره امتحان کنید."


def sign_in(user: dict) -> None:
    token = sessions.create_session(user["id"])
    browser_store.save(token)
    st.session_state.pop(AUTH_CACHE, None)
    st.rerun()


def sign_out(token: str) -> None:
    sessions.revoke(token)
    browser_store.clear()
    for key in (AUTH_CACHE, "user", "chats", "selected_assistant"):
        st.session_state.pop(key, None)
    st.rerun()


def current_session_user(token: str) -> dict | None:
    """برای کم کردن رفت‌وبرگشت به دیتابیس، نتیجه تا یک دقیقه در همین نشست نگه داشته می‌شود؛
    نشست باطل یا کاربر حذف‌شده حداکثر بعد از یک دقیقه خارج می‌شود."""
    cached = st.session_state.get(AUTH_CACHE)
    if cached and cached["token"] == token and time.monotonic() - cached["at"] < SESSION_RECHECK_SECONDS:
        return cached["user"]
    user = sessions.user_for_session(token)
    st.session_state[AUTH_CACHE] = {"token": token, "user": user, "at": time.monotonic()} if user else None
    return user


def login_screen() -> None:
    st.title("🤖 AssistantLab")
    st.caption("دستیار هوشمند سازمان خود را بر پایه‌ی اسناد خودتان بسازید.")

    tab_login, tab_register = st.tabs(["ورود", "ثبت سازمان جدید"])

    with tab_login:
        with st.form("login"):
            username = st.text_input("نام کاربری")
            password = st.text_input("رمز عبور", type="password")
            if st.form_submit_button("ورود", type="primary"):
                try:
                    user = db.get_user_by_username(username.strip())
                    if user and auth.verify_password(password, user["password_hash"]):
                        sign_in(user)
                    st.error("نام کاربری یا رمز عبور اشتباه است.")
                except Exception:  # قطع موقت اتصال؛ جزئیات فقط در لاگ سرور
                    st.error(DB_UNAVAILABLE)

    with tab_register:
        st.write("با ثبت سازمان، شما مدیر آن می‌شوید و می‌توانید دستیار بسازید و اعضا را اضافه کنید.")
        with st.form("register"):
            org_name = st.text_input("نام سازمان")
            display_name = st.text_input("نام شما")
            username = st.text_input("نام کاربری (انگلیسی)")
            password = st.text_input("رمز عبور", type="password")
            password2 = st.text_input("تکرار رمز عبور", type="password")
            if st.form_submit_button("ثبت سازمان", type="primary"):
                username = username.strip()
                error = auth.validate_new_account(username, password)
                if not org_name.strip() or not display_name.strip():
                    error = "نام سازمان و نام شما را وارد کنید."
                elif password != password2:
                    error = "رمزهای عبور یکسان نیستند."
                # تکراری بودن نام کاربری هنگام ثبت (DuplicateError) بررسی می‌شود
                if error:
                    st.error(error)
                else:
                    try:
                        user = db.create_org_with_admin(
                            org_name.strip(), username, display_name.strip(), auth.hash_password(password)
                        )
                        sign_in(user)
                    except db.DuplicateError as e:
                        st.error(str(e))
                    except Exception:
                        st.error(DB_UNAVAILABLE)


with perf.timed("session user"):
    user = current_session_user(stored_token) if stored_token else None
if not user:
    st.session_state.pop("user", None)
    st.navigation(list(PAGES.values()), position="hidden")  # منوی صفحه‌ها در صفحه‌ی ورود نمایش داده نمی‌شود
    login_screen()
    st.stop()
st.session_state["user"] = user

pages = [PAGES["chat"]]
if user["role"] == "admin":
    pages += [PAGES["assistants"], PAGES["sources"], PAGES["team"]]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(f"**{user['org_name']}**")
    st.caption(f"{user['display_name']} · {'مدیر' if user['role'] == 'admin' else 'عضو'}")
    if not any(config.PROVIDER_KEYS.values()):
        st.warning("هیچ کلید مدل زبانی تنظیم نشده است (GROQ_API_KEY یا GEMINI_API_KEY).")
    if st.button("خروج", icon=":material/logout:"):
        sign_out(stored_token)

nav.run()
perf.log(f"== full rerun ({nav.title})", (time.perf_counter() - _run_started) * 1000)
