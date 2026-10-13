"""بررسی کلیدها و مدل‌ها: python scripts/check_models.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import llm  # noqa: E402

for provider, key in config.PROVIDER_KEYS.items():
    if not key:
        continue
    try:
        models = llm.list_models(provider)
        print(f"{provider}: {len(models)} مدل در دسترس")
    except Exception as e:
        print(f"{provider}: خطا در کلید یا اتصال: {e}")

print()
print(f"آزمایش Embedding با {config.EMBED_MODEL} ...")
print(f"  OK — ابعاد بردار: {llm.embed(['سلام دنیا']).shape[1]}")

print()
print("مدل‌های گفتگو به ترتیب اولویت (CHAT_MODELS):")
for target in llm.chat_targets():
    config.CHAT_MODELS = str(target)  # هر مدل جداگانه
    started = time.perf_counter()
    try:
        reply = "".join(llm.stream_chat([{"role": "user", "content": "فقط بنویس: سلام"}])).strip()
        print(f"  {target}: OK در {time.perf_counter() - started:.1f} ثانیه — {reply[:30]}")
    except Exception as e:
        print(f"  {target}: خطا — {type(e).__name__}: {str(e)[:100]}")
