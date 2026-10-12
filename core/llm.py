"""اتصال به مدل‌ها از طریق API سازگار با OpenAI (Gemini، Groq، OpenRouter، ...)."""
from collections.abc import Iterator
from functools import lru_cache

import numpy as np
from openai import OpenAI

import config

EMBED_BATCH = 50
MAX_EMBED_CHARS = 6000


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


def stream_chat(messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
    stream = chat_client().chat.completions.create(
        model=config.CHAT_MODEL, messages=messages, temperature=temperature, stream=True,
    )
    for event in stream:
        if event.choices and event.choices[0].delta.content:
            yield event.choices[0].delta.content


def list_models() -> list[str]:
    return sorted(m.id for m in chat_client().models.list())
