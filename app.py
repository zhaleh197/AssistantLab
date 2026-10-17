"""نقطه‌ی ورود سرور: streamlit run app.py

رابط کاربری در home.py است؛ اینجا فقط یک مسیر عیب‌یابی برای انتشار اضافه می‌شود.
"""
from pathlib import Path

import streamlit as st
from starlette.responses import JSONResponse
from starlette.routing import Route

import config  # تنظیمات محیطی و Secrets، از جمله اصلاح SSL_CERT_FILE
from core import db


def status(request):
    """عیب‌یابی انتشار: فقط بله/خیر، بدون هیچ مقدار محرمانه."""
    return JSONResponse({
        "storage": "postgres" if db.is_postgres() else "sqlite (temporary)",
        "streamlit_version": st.__version__,
        "chat_providers_with_key": sorted(p for p, k in config.PROVIDER_KEYS.items() if k),
        "embedding_key_set": bool(config.EMBED_API_KEY),
    })


db.init_db()

app = st.App(Path(__file__).parent / "home.py", routes=[Route("/status", status)])
