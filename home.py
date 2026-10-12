"""رابط کاربری اصلی (از طریق app.py اجرا می‌شود: streamlit run app.py)"""
import json
import time

import streamlit as st

import config
from core import auth, db, perf, sessions

_run_started = time.perf_counter()
from core.ui import apply_style

st.set_page_config(page_title="AssistantLab", page_icon="🤖", layout="wide")
apply_style()
try:
    with perf.timed("init_db"):
        db.init_db()
except Exception as e:  # تنظیمات اشتباه DATABASE_URL یا قطع اتصال
    st.error(f"اتصال به دیتابیس برقرار نشد: {e}")
    st.stop()


def redirect(url: str) -> None:
    """انتقال مرورگر به مسیرهای ورود/خروج سرور (app.py) که کوکی را تنظیم می‌کنند.
    آدرس نسبی است تا وقتی برنامه زیر یک مسیر پایه اجرا می‌شود (مثل /~/+/ در Streamlit Cloud) هم درست کار کند."""
    st.html(f"<script>window.location.replace({json.dumps(url)});</script>", unsafe_allow_javascript=True)
    st.info("در حال انتقال...")
    st.link_button("اگر منتقل نشدید، اینجا را بزنید", url)
    st.stop()


def sign_in(user_id: int) -> None:
    redirect(f"auth/finish?ticket={sessions.create_ticket(user_id)}")


def login_screen() -> None:
    st.title("🤖 AssistantLab")
    st.caption("دستیار هوشمند سازمان خود را بر پایه‌ی اسناد خودتان بسازید.")

    tab_login, tab_register = st.tabs(["ورود", "ثبت سازمان جدید"])

    with tab_login:
        with st.form("login"):
            username = st.text_input("نام کاربری")
            password = st.text_input("رمز عبور", type="password")
            if st.form_submit_button("ورود", type="primary"):
                user = db.get_user_by_username(username.strip())
                if user and auth.verify_password(password, user["password_hash"]):
                    sign_in(user["id"])
                st.error("نام کاربری یا رمز عبور اشتباه است.")

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
                elif not error and db.username_exists(username):
                    error = "این نام کاربری قبلاً ثبت شده است."
                if error:
                    st.error(error)
                else:
                    try:
                        user = db.create_org_with_admin(
                            org_name.strip(), username, display_name.strip(), auth.hash_password(password)
                        )
                    except db.DuplicateError as e:
                        st.error(str(e))
                    else:
                        sign_in(user["id"])


SESSION_RECHECK_SECONDS = 60


def current_session_user() -> dict | None:
    """کاربر از روی کوکی نشست شناسایی می‌شود. برای کم کردن رفت‌وبرگشت به دیتابیس، نتیجه تا
    یک دقیقه در همین نشست مرورگر نگه داشته می‌شود؛ نشست باطل یا کاربر حذف‌شده حداکثر بعد از
    یک دقیقه خارج می‌شود."""
    token = st.context.cookies.get(sessions.COOKIE_NAME)
    cached = st.session_state.get("_auth_cache")
    if cached and cached["token"] == token and time.monotonic() - cached["at"] < SESSION_RECHECK_SECONDS:
        return cached["user"]
    user = sessions.user_for_session(token)
    st.session_state["_auth_cache"] = {"token": token, "user": user, "at": time.monotonic()} if user else None
    return user


with perf.timed("session user"):
    user = current_session_user()
if not user:
    st.session_state.pop("user", None)
    login_screen()
    st.stop()
st.session_state["user"] = user

pages = [st.Page("views/chat.py", title="گفتگو", icon=":material/chat:", default=True)]
if user["role"] == "admin":
    pages += [
        st.Page("views/assistants.py", title="دستیارها", icon=":material/smart_toy:"),
        st.Page("views/sources.py", title="منابع", icon=":material/library_books:"),
        st.Page("views/team.py", title="اعضای سازمان", icon=":material/group:"),
    ]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(f"**{user['org_name']}**")
    st.caption(f"{user['display_name']} · {'مدیر' if user['role'] == 'admin' else 'عضو'}")
    if not config.CHAT_API_KEY:
        st.warning("کلید API تنظیم نشده است (فایل .env).")
    if st.button("خروج", icon=":material/logout:"):
        st.session_state.clear()
        redirect("auth/logout")

nav.run()
perf.log(f"== full rerun ({nav.title})", (time.perf_counter() - _run_started) * 1000)
