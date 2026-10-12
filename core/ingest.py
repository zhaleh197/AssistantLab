"""خط لوله‌ی افزودن منبع: استخراج ← تکه‌تکه کردن ← Embedding ← ذخیره."""
import config
from core import db, llm
from core.text import chunk_text

Segments = list[tuple[str, str]]


class QuotaExceeded(RuntimeError):
    pass


def ingest(org_id: int, assistant_id: int, kind: str, name: str, segments: Segments) -> int:
    """منبع را ثبت و پردازش می‌کند و تعداد تکه‌ها را برمی‌گرداند.
    در صورت خطا وضعیت منبع «error» می‌شود و خطا دوباره پرتاب می‌شود."""
    source_id = db.create_source(org_id, assistant_id, kind, name, config.EMBED_MODEL)
    try:
        items = [
            (loc, chunk)
            for loc, text in segments
            for chunk in chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        ]
        if not items:
            raise ValueError("متنی برای افزودن پیدا نشد.")
        if db.count_org_chunks(org_id) + len(items) > config.MAX_CHUNKS_PER_ORG:
            raise QuotaExceeded("سهمیه‌ی حجم منابع سازمان شما پر شده است.")

        # نام منبع کنار متن embed می‌شود تا جستجو زمینه‌ی تکه را هم بداند
        vectors = llm.embed([f"{name}\n{loc}\n{text}".strip() for loc, text in items])
        db.add_chunks(org_id, assistant_id, source_id, items, vectors)
        db.set_source_status(source_id, "ready", n_chunks=len(items))
        return len(items)
    except Exception as e:
        try:
            db.set_source_status(source_id, "error", error=str(e)[:500])
        except Exception:
            pass  # اگر خود دیتابیس در دسترس نیست، خطای اصلی مهم‌تر است و نباید پنهان شود
        raise
