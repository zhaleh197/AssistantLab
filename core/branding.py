"""برند هر سازمان: رنگ اصلی و آواتار دستیار.

از یک رنگ، همه‌ی رنگ‌های گفتگو ساخته می‌شوند (گرادیان، حباب، برچسب‌ها) و خوانایی متن روی آن
بررسی می‌شود. تصویر بارگذاری‌شده همیشه دوباره رمزگذاری می‌شود (PNG مربعی ۲۵۶ پیکسلی)، پس فایل
مخرب یا SVG حاوی کد هرگز مستقیم به صفحه نمی‌رسد.
"""
import base64
import colorsys
import html
import io
import re

DEFAULT_COLOR = "#6366f1"
AVATAR_MODES = ("sparkle", "initial", "image")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = 256
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class InvalidImage(ValueError):
    pass


# ---------- رنگ ----------

def normalize_color(value: str | None) -> str:
    return value.lower() if value and _HEX.match(value) else DEFAULT_COLOR


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = normalize_color(hex_color).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in rgb)


def luminance(hex_color: str) -> float:
    """روشنایی نسبی (WCAG)."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def shift(hex_color: str, hue: float = 0.0, light: float = 0.0, sat: float = 0.0) -> str:
    """چرخش رنگ (درجه) و تغییر روشنی/اشباع."""
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_color))
    return _hex(colorsys.hls_to_rgb((h + hue / 360) % 1, max(0, min(1, l + light)), max(0, min(1, s + sat))))


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (round(c * 255) for c in _rgb(hex_color))
    return f"rgba({r}, {g}, {b}, {alpha})"


def text_color_for(hex_color: str, background: str, target: float = 4.5) -> str:
    """رنگ متنی هم‌خانواده‌ی برند که روی background کنتراست کافی دارد."""
    color = normalize_color(hex_color)
    step = -0.05 if luminance(background) > 0.5 else 0.05
    for _ in range(20):
        if contrast(color, background) >= target:
            return color
        color = shift(color, light=step)
    return "#1d2033" if luminance(background) > 0.5 else "#e6e8f2"


def palette(hex_color: str) -> dict:
    """رنگ‌های گفتگو از روی رنگ برند."""
    c = normalize_color(hex_color)
    return {
        "brand": c,
        "brand-2": shift(c, hue=28, light=0.03),           # انتهای گرادیان
        "brand-3": shift(c, hue=62, light=0.06),           # سومین رنگ آواتار
        # متن داخل حباب کاربر: سفید روی رنگ تیره، تیره روی رنگ روشن
        "on-brand": "#ffffff" if contrast("#ffffff", c) >= 3 else "#1d2033",
        "glow": rgba(c, 0.13),
        "glow-dark": rgba(shift(c, light=0.15), 0.16),
        "chip-bg": rgba(c, 0.08),
        "chip-bg-dark": rgba(shift(c, light=0.15), 0.14),
        "chip-border": rgba(c, 0.22),
        "chip-text": text_color_for(c, "#ffffff"),
        "chip-text-dark": text_color_for(c, "#171a26"),
        "shadow": rgba(c, 0.55),
        "hover-border": rgba(c, 0.65),
    }


# ---------- آواتار ----------

# کلمه‌های عمومی اول نام که حرف اول آواتار را از آن‌ها برنمی‌داریم («دستیار اکام» ← «ا»)
_GENERIC_WORDS = {"دستیار", "شرکت", "سازمان", "گروه", "موسسه", "مؤسسه", "بانک", "assistant", "the", "company"}


def initial_of(name: str) -> str:
    words = name.split()
    for word in words:
        if word.lower() not in _GENERIC_WORDS:
            return word[0].upper()
    return words[0][0].upper() if words else "?"


def _svg_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def avatar_uri(color: str, mode: str = "sparkle", name: str = "", image: str = "") -> str:
    """آدرس داده‌ای (data URI) آواتار دستیار برای استفاده در <img> و st.chat_message."""
    if mode == "image" and image.startswith("data:image/png;base64,"):
        return image
    p = palette(color)
    gradient = f"""<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{p['brand']}"/><stop offset=".55" stop-color="{p['brand-2']}"/>
<stop offset="1" stop-color="{p['brand-3']}"/></linearGradient></defs>
<rect width="64" height="64" rx="20" fill="url(#g)"/>"""
    fg = p["on-brand"]
    if mode == "initial" and name.strip():
        letter = html.escape(initial_of(name))
        body = (f'<text x="32" y="33" text-anchor="middle" dominant-baseline="central" font-size="30" '
                f'font-weight="700" font-family="Vazirmatn, Tahoma, sans-serif" fill="{fg}">{letter}</text>')
    else:
        body = (f'<path d="M32 13c1.6 8.6 6.4 13.4 15 15-8.6 1.6-13.4 6.4-15 15-1.6-8.6-6.4-13.4-15-15 '
                f'8.6-1.6 13.4-6.4 15-15z" fill="{fg}"/>'
                f'<path d="M46 39c.7 3.7 2.8 5.8 6.5 6.5-3.7.7-5.8 2.8-6.5 6.5-.7-3.7-2.8-5.8-6.5-6.5 '
                f'3.7-.7 5.8-2.8 6.5-6.5z" fill="{fg}" opacity=".85"/>')
    return _svg_uri(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{gradient}{body}</svg>')


LOGO_BACKGROUNDS = ("white", "brand", "transparent")
SOURCE_MAX_SIZE = 512          # نسخه‌ی اصلی لوگو برای تنظیم دوباره‌ی حاشیه و پس‌زمینه بدون بارگذاری مجدد
DEFAULT_PADDING = 12           # درصد حاشیه‌ی خالی دور لوگو در هر طرف
_PNG_PREFIX = "data:image/png;base64,"


def _to_uri(img) -> str:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return _PNG_PREFIX + base64.b64encode(out.getvalue()).decode()


def _from_uri(uri: str):
    from PIL import Image

    if not uri.startswith(_PNG_PREFIX):
        raise InvalidImage("لوگو پیدا نشد؛ دوباره بارگذاری کنید.")
    return Image.open(io.BytesIO(base64.b64decode(uri[len(_PNG_PREFIX):]))).convert("RGBA")


def _trim(img):
    """فضای خالی دور لوگو را حذف می‌کند: با پس‌زمینه‌ی شفاف بر اساس شفافیت، وگرنه بر اساس رنگ گوشه‌ی تصویر."""
    from PIL import Image, ImageChops

    alpha = img.getchannel("A")
    if alpha.getextrema()[0] < 250:
        bbox = alpha.point(lambda a: 255 if a > 8 else 0).getbbox()
    else:
        rgb = img.convert("RGB")
        background = Image.new("RGB", img.size, rgb.getpixel((0, 0)))
        diff = ImageChops.difference(rgb, background).convert("L").point(lambda v: 255 if v > 18 else 0)
        bbox = diff.getbbox()
    return img.crop(bbox) if bbox else img


def prepare_logo(data: bytes) -> str:
    """لوگوی بارگذاری‌شده را بررسی، از نو رمزگذاری و از حاشیه‌ی خالی پاک می‌کند (نسخه‌ی اصلی، PNG)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImage("حجم تصویر باید کمتر از ۲ مگابایت باشد.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ("PNG", "JPEG", "WEBP"):
                raise InvalidImage("فقط تصویر PNG، JPG یا WEBP قابل قبول است.")
            img = _trim(ImageOps.exif_transpose(img).convert("RGBA"))
            img.thumbnail((SOURCE_MAX_SIZE, SOURCE_MAX_SIZE), Image.Resampling.LANCZOS)
            return _to_uri(img)
    except (UnidentifiedImageError, OSError) as e:
        raise InvalidImage("این فایل تصویر معتبری نیست.") from e


def compose_logo_avatar(source_uri: str, background: str = "white", padding: int = DEFAULT_PADDING,
                        color: str = DEFAULT_COLOR) -> str:
    """کل لوگو (بدون برش) با حفظ نسبت ابعاد، وسط یک مربع ۲۵۶ پیکسلی با حاشیه و پس‌زمینه‌ی انتخابی."""
    from PIL import Image, ImageDraw, ImageOps

    logo = _from_uri(source_uri)
    padding = max(0, min(30, int(padding)))
    inner = round(AVATAR_SIZE * (1 - 2 * padding / 100))
    logo = ImageOps.contain(logo, (inner, inner), method=Image.Resampling.LANCZOS)

    if background == "brand":
        p = palette(color)
        canvas = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE))
        draw = ImageDraw.Draw(canvas)
        start, end = _rgb(p["brand"]), _rgb(p["brand-2"])
        for y in range(AVATAR_SIZE):  # گرادیان قطری ساده از رنگ برند
            t = y / (AVATAR_SIZE - 1)
            draw.line([(0, y), (AVATAR_SIZE, y)],
                      fill=tuple(round((a + (b - a) * t) * 255) for a, b in zip(start, end)) + (255,))
    elif background == "transparent":
        canvas = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 255))

    offset = ((AVATAR_SIZE - logo.width) // 2, (AVATAR_SIZE - logo.height) // 2)
    canvas.alpha_composite(logo, offset)
    return _to_uri(canvas)


def from_org(org: dict | None) -> dict:
    """تنظیمات برند یک سازمان (یا پیش‌فرض‌ها)."""
    org = org or {}
    return {
        "color": normalize_color(org.get("brand_color")),
        "mode": org.get("avatar_mode") if org.get("avatar_mode") in AVATAR_MODES else "sparkle",
        "image": org.get("avatar_image") or "",
        "source": org.get("avatar_source") or "",
        "background": org.get("avatar_bg") if org.get("avatar_bg") in LOGO_BACKGROUNDS else "white",
        "padding": int(org.get("avatar_padding") if org.get("avatar_padding") is not None else DEFAULT_PADDING),
    }
