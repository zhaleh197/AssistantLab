# برای Hugging Face Spaces (Docker). Space برنامه را با کاربر غیر root (UID 1000) روی پورت 7860 اجرا می‌کند.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # مرورگر Playwright در مسیری مشترک نصب می‌شود تا کاربر 1000 هم به آن دسترسی داشته باشد
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
    && playwright install --with-deps chromium-headless-shell \
    && chmod -R a+rX /opt/ms-playwright

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # فقط اگر DATABASE_URL تنظیم نشده باشد استفاده می‌شود (SQLite موقت؛ با ری‌استارت پاک می‌شود)
    DATA_DIR=/tmp/assistantlab-data
WORKDIR /home/user/app
COPY --chown=user . .

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true"]
