"""پیش‌پردازش متن: یکسان‌سازی فارسی، توکن‌سازی برای BM25 و تکه‌تکه کردن."""
import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه",
    "أ": "ا", "إ": "ا", "ٱ": "ا",
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # ارقام فارسی
    **{chr(0x0660 + i): str(i) for i in range(10)},  # ارقام عربی
})
_DIACRITICS = re.compile(r"[ً-ٰٟـ]")  # اعراب و کشیده
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f‎‏﻿]")
_SPACES = re.compile(r"[ \t ]+")
_WORD = re.compile(r"\w+")
_ZWNJ = "‌"


def clean(text: str) -> str:
    """یکسان‌سازی برای ذخیره و نمایش (نیم‌فاصله حفظ می‌شود)."""
    text = _CONTROL.sub("", text).translate(_CHAR_MAP)
    text = _DIACRITICS.sub("", text)
    text = _SPACES.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def tokenize(text: str) -> list[str]:
    """توکن‌ها برای جستجوی کلیدواژه‌ای. نیم‌فاصله حذف می‌شود تا «می‌روم» و «میروم» یکی شوند."""
    text = clean(text).replace(_ZWNJ, "").lower()
    return _WORD.findall(text)


def _hard_split(text: str, size: int) -> list[str]:
    out = []
    while len(text) > size:
        cut = text.rfind(" ", 0, size)
        cut = cut if cut > size // 2 else size
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def _units(text: str, size: int) -> list[str]:
    """تقسیم به پاراگراف؛ پاراگراف‌های بلند به جمله و در نهایت برش سخت."""
    units = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            units.append(para)
            continue
        for sent in re.split(r"(?<=[.!?؟؛])\s+|\n", para):
            sent = sent.strip()
            if sent:
                units.extend(_hard_split(sent, size) if len(sent) > size else [sent])
    return units


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    text = clean(text)
    chunks: list[str] = []
    cur = ""
    for unit in _units(text, size):
        if cur and len(cur) + len(unit) + 1 > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap > 0 else ""
            if tail and len(cur) > overlap:
                space = tail.find(" ")
                tail = tail[space + 1:] if space != -1 else ""
            cur = f"{tail}\n{unit}".strip() if tail else unit
        else:
            cur = f"{cur}\n{unit}" if cur else unit
    if cur.strip():
        chunks.append(cur.strip())
    return chunks
