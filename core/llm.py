"""اتصال به مدل‌ها از طریق API سازگار با OpenAI (Gemini، Groq، OpenRouter، ...)."""
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from openai import (
    APIConnectionError, APITimeoutError, InternalServerError, NotFoundError, OpenAI, RateLimitError,
)

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
    provider: str
    model: str

    @property
    def base_url(self) -> str:
        return config.PROVIDER_URLS[self.provider]

    @property
    def api_key(self) -> str:
        return config.PROVIDER_KEYS.get(self.provider, "")

    def extra_params(self) -> dict:
        # مدل‌های «فکرکننده» پیش از پاسخ استدلال می‌کنند؛ برای پاسخ از روی منابع لازم نیست و کندی دارد
        if self.provider == "gemini" and config.GEMINI_REASONING_EFFORT:
            return {"reasoning_effort": config.GEMINI_REASONING_EFFORT}
        if self.model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low"}
        return {}

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def chat_targets() -> list[ChatTarget]:
    """مدل‌های CHAT_MODELS به ترتیب؛ مدلی که سرویسش ناشناخته است یا کلیدش تنظیم نشده کنار گذاشته می‌شود."""
    targets = []
    for item in config.CHAT_MODELS.split(","):
        provider, sep, model = item.strip().partition(":")
        if not sep or not model or provider not in config.PROVIDER_URLS:
            continue
        target = ChatTarget(provider, model.strip())
        if target.api_key and target not in targets:
            targets.append(target)
    if not targets:
        raise MissingApiKey("هیچ مدل گفتگویی با کلید معتبر تنظیم نشده است (GROQ_API_KEY یا GEMINI_API_KEY).")
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
        except (*TRANSIENT_ERRORS, NotFoundError) as e:
            if started:  # بخشی از پاسخ نمایش داده شده؛ شروع دوباره با مدل دیگر گیج‌کننده است
                raise
            if isinstance(e, NotFoundError):  # مدل بازنشسته یا اشتباه؛ مدل بعدی امتحان می‌شود
                print(f"chat model not found, skipping: {target}", file=sys.stderr)
            last_error = e
    raise last_error


def list_models(provider: str) -> list[str]:
    client = _client(config.PROVIDER_URLS[provider], config.PROVIDER_KEYS.get(provider, ""))
    return sorted(m.id for m in client.models.list())
