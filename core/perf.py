"""زمان‌سنجی مراحل برای پیدا کردن کندی. با PERF_LOG=1 در خروجی سرور چاپ می‌شود؛ در حالت عادی هیچ کاری نمی‌کند."""
import os
import sys
import time
from contextlib import contextmanager

ENABLED = os.getenv("PERF_LOG") == "1"


def log(label: str, ms: float) -> None:
    if ENABLED:
        print(f"[perf] {label:<28} {ms:7.0f} ms", file=sys.stderr, flush=True)


@contextmanager
def timed(label: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        log(label, (time.perf_counter() - start) * 1000)
