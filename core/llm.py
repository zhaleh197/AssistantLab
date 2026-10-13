"""اتصال به مدل‌ها از طریق API سازگار با OpenAI (Gemini، Groq، OpenRouter، ...)."""
from collections.abc import Iterator
from dataclasses import dataclass
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
        client = client.with_options(max_retries=1, timeout=10)
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


@dataclass(frozen=True)
class ChatTarget:
    base_url: str
    api_key: str
    model: str

    def extra_params(self) -> dict:
        # مدل‌های جدید Gemini پیش از پاسخ «فکر» می‌کنند؛ برای پاسخ از روی منابع لازم نیست و چند ثانیه کندی دارد
        if "generativelanguage.googleapis.com" in self.base_url and config.GEMINI_REASONING_EFFORT:
            return {"reasoning_effort": config.GEMINI_REASONING_EFFORT}
        return {}


def chat_targets() -> list[ChatTarget]:
    """مدل اصلی و (در صورت تنظیم) مدل جایگزین؛ جایگزین می‌تواند از سرویس دیگری با کلید خودش باشد."""
    targets = [ChatTarget(config.CHAT_BASE_URL, config.CHAT_API_KEY, config.CHAT_MODEL)]
    if config.CHAT_FALLBACK_MODEL:
        fallback = ChatTarget(
            config.CHAT_FALLBACK_BASE_URL or config.CHAT_BASE_URL,
            config.CHAT_FALLBACK_API_KEY or config.CHAT_API_KEY,
            config.CHAT_FALLBACK_MODEL,
        )
        if fallback != targets[0]:
            targets.append(fallback)
    return targets


def stream_chat(messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
    """مدل‌های پلن رایگان گاهی شلوغ‌اند و تا یک دقیقه جواب نمی‌دهند. اگر مدل اصلی خطا بدهد یا در
    CHAT_FIRST_TOKEN_TIMEOUT ثانیه شروع به پاسخ نکند، فوراً مدل جایگزین امتحان می‌شود."""
    targets = chat_targets()
    last_error: Exception | None = None
    for i, target in enumerate(targets):
        is_last = i == len(targets) - 1
        # در جریان (stream)، مهلت خواندن یعنی حداکثر انتظار برای هر تکه‌ی پاسخ، از جمله اولین کلمه
        client = _client(target.base_url, target.api_key).with_options(
            max_retries=1 if is_last else 0,
            timeout=config.CHAT_LAST_MODEL_TIMEOUT if is_last else config.CHAT_FIRST_TOKEN_TIMEOUT,
        )
        started = False
        try:
            stream = client.chat.completions.create(
                model=target.model, messages=messages, temperature=temperature, stream=True,
                **target.extra_params(),
            )
            for event in stream:
                if event.choices and event.choices[0].delta.content:
                    started = True
                    yield event.choices[0].delta.content
            return
        except TRANSIENT_ERRORS as e:
            if started:  # بخشی از پاسخ نمایش داده شده؛ شروع دوباره با مدل دیگر گیج‌کننده است
                raise
            last_error = e
    raise last_error


def list_models() -> list[str]:
    return sorted(m.id for m in chat_client().models.list())
