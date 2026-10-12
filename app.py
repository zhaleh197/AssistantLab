"""نقطه‌ی ورود سرور: streamlit run app.py

رابط کاربری در home.py است؛ اینجا فقط مسیرهای ورود/خروج اضافه می‌شوند،
چون تنظیم کوکی ماندگار از داخل Streamlit ممکن نیست.
"""
from pathlib import Path

import streamlit as st
from starlette.responses import RedirectResponse
from starlette.routing import Route

import config  # noqa: F401  (تنظیمات محیطی، از جمله اصلاح SSL_CERT_FILE)
from core import db, sessions


# بازگشت نسبی به صفحه‌ی اصلی: از /auth/finish به / و از /~/+/auth/finish (Streamlit Cloud) به /~/+/
HOME = "../"


def _is_https(request) -> bool:
    # پشت پراکسی (Hugging Face و ...) پروتکل واقعی در این هدر است
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def auth_finish(request):
    token = sessions.exchange_ticket(request.query_params.get("ticket", ""))
    response = RedirectResponse(HOME, status_code=303)
    if token:
        secure = _is_https(request)
        response.set_cookie(
            sessions.COOKIE_NAME, token,
            max_age=sessions.SESSION_TTL, path="/", httponly=True, secure=secure,
            # روی https با SameSite=None تا داخل iframe (مثل صفحه‌ی Hugging Face) هم کار کند
            samesite="none" if secure else "lax",
        )
    return response


def auth_logout(request):
    sessions.revoke(request.cookies.get(sessions.COOKIE_NAME))
    response = RedirectResponse(HOME, status_code=303)
    secure = _is_https(request)
    response.delete_cookie(
        sessions.COOKIE_NAME, path="/", httponly=True, secure=secure, samesite="none" if secure else "lax",
    )
    return response


db.init_db()

app = st.App(
    Path(__file__).parent / "home.py",
    routes=[Route("/auth/finish", auth_finish), Route("/auth/logout", auth_logout)],
)
