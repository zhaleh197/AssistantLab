# برای Hugging Face Spaces (Docker) — پورت 7860
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium-headless-shell
COPY . .
ENV DATA_DIR=/data
RUN mkdir -p /data && chmod 777 /data
EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]
