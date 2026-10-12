"""اتصال به مدل‌ها از طریق API سازگار با OpenAI (Gemini، Groq، OpenRouter، ...)."""
from collections.abc import Iterator
from functools import lru_cache

import numpy as np
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

import config

EMBED_BATCH = 50
MAX_EMBED_CHARS = 6000

# خطاهایی که با رفتن سراغ مدل جایگزین حل می‌شوند (سهمیه، شلوغی، قطعی)
TRANSIENT_ERRORS = (RateLimitError, InternalServerError, APITimeoutError, APIConnectionError)


class MissingApiKey(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _client(base_url: str, api_key: str) -> OpenAI:
    if not api_key:
        raise MissingApiKey("کلید API تنظیم نشده است. فایل .env را طبق README پر کنید.")
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=5, timeout=120)


def chat_client() -> OpenAI:
    return _client(config.CHAT_BASE_URL, config.CHAT_API_KEY)


def embed_client() -> OpenAI:
    return _client(config.EMBED_BASE_URL, config.EMBED_API_KEY)


def embed(texts: list[str]) -> np.ndarray:
    """بردارهای نرمال‌شده (طول ۱) برمی‌گرداند تا ضرب داخلی همان شباهت کسینوسی باشد."""
    client = embed_client()
    if len(texts) == 1:
        # بردار سؤال کاربر: کاربر منتظر است، پس تلاش مجدد کوتاه؛ برای افزودن منابع صبر بیشتر
        client = client.with_options(max_retries=2, timeout=20)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = [t[:MAX_EMBED_CHARS] for t in texts[i:i + EMBED_BATCH]]
        extra = {"dimensions": config.EMBED_DIMENSIONS} if config.EMBED_DIMENSIONS else {}
        resp = client.embeddings.create(model=config.EMBED_MODEL, input=batch, **extra)
        if len(resp.data) != len(batch):
            raise RuntimeError(f"سرویس Embedding برای {len(batch)} متن، {len(resp.data)} بردار برگرداند.")
        # Gemini برای اولین مورد index را خالی (None) می‌فرستد؛ None همان 0 است
        vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index or 0))
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.where(norms == 0, 1, norms)


def chat_models() -> list[str]:
    models = [config.CHAT_MODEL]
    if config.CHAT_FALLBACK_MODEL and config.CHAT_FALLBACK_MODEL != config.CHAT_MODEL:
        models.append(config.CHAT_FALLBACK_MODEL)
    return models


def stream_chat(messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
    """اگر مدل اصلی شلوغ یا بیش از سهمیه باشد، به‌جای تلاش‌های طولانی فوراً مدل جایگزین امتحان می‌شود."""
    client = chat_client().with_options(max_retries=1, timeout=60)
    last_error: Exception | None = None
    for model in chat_models():
        try:
            stream = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, stream=True,
            )
        except TRANSIENT_ERRORS as e:
            last_error = e
            continue
        for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content
        return
    raise last_error


def list_models() -> list[str]:
    return sorted(m.id for m in chat_client().models.list())
