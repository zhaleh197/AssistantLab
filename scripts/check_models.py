"""بررسی کلید API و نمایش مدل‌های در دسترس: python scripts/check_models.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import llm  # noqa: E402

print("مدل‌های در دسترس:")
for name in llm.list_models():
    print("  ", name)

print(f"\nآزمایش Embedding با {config.EMBED_MODEL} ...")
vec = llm.embed(["سلام دنیا"])
print(f"  OK — ابعاد بردار: {vec.shape[1]}")

print(f"\nآزمایش گفتگو با {config.CHAT_MODEL} ...")
reply = "".join(llm.stream_chat([{"role": "user", "content": "فقط بنویس: سلام"}]))
print("  OK —", reply.strip())
