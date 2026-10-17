"""تنظیم رنگ و آواتار دستیارهای سازمان، با پیش‌نمایش زنده."""
import html

import streamlit as st

from core import branding, chat_style, db
from core.ui import BRAND_CACHE, require_admin

user = require_admin()
org_id = user["org_id"]
org = db.get_org(org_id)
saved = branding.from_org(org)

MODE_LABELS = {"sparkle": "نشان درخشش", "initial": "حرف اول نام", "image": "لوگوی سازمان"}
LOGO_BG_LABELS = {"white": "سفید", "brand": "رنگ برند", "transparent": "شفاف"}
PRESETS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6", "#0f172a"]

st.title("ظاهر و برند", icon=":material/palette:")
st.caption("رنگ و آواتار دستیارهای سازمان در صفحه‌ی گفتگو و لینک‌های عمومی.")

settings, preview = st.columns([1, 1], gap="large")

with settings:
    with st.container(border=True):
        st.subheader("رنگ اصلی", icon=":material/format_color_fill:")
        if "brand_color_input" not in st.session_state:
            st.session_state["brand_color_input"] = saved["color"]
        st.caption("رنگ‌های پیشنهادی")
        with st.container(horizontal=True, gap="small"):
            for preset in PRESETS:
                if st.button(" ", key=f"preset_{preset.lstrip('#')}", help=preset):
                    st.session_state["brand_color_input"] = preset
        color = st.color_picker("رنگ دلخواه", key="brand_color_input")

    with st.container(border=True):
        st.subheader("آواتار دستیار", icon=":material/account_circle:")
        mode = st.segmented_control(
            "نوع آواتار", list(MODE_LABELS), format_func=MODE_LABELS.get,
            default=saved["mode"], key="avatar_mode_input", required=True,
        )
        source, image = saved["source"], saved["image"]
        background, padding = saved["background"], saved["padding"]
        if mode == "image":
            upload = st.file_uploader("لوگو (PNG، JPG یا WEBP؛ حداکثر ۲ مگابایت)", type=["png", "jpg", "jpeg", "webp"])
            if upload is not None:
                try:
                    source = branding.prepare_logo(upload.getvalue())
                except branding.InvalidImage as e:
                    st.error(str(e), icon=":material/broken_image:")
            if source:
                st.caption("کل لوگو بدون برش و با حفظ نسبت ابعاد وسط آیکون قرار می‌گیرد؛ حاشیه‌ی خالی دورش خودکار حذف می‌شود.")
                background = st.segmented_control(
                    "پس‌زمینه‌ی آیکون", list(LOGO_BG_LABELS), format_func=LOGO_BG_LABELS.get,
                    default=background, key="logo_bg_input", required=True,
                )
                padding = st.slider(
                    "فاصله‌ی لوگو از لبه‌ی آیکون", 0, 30, value=padding, format="%d٪", key="logo_padding_input",
                    help="عدد کمتر یعنی لوگو بزرگ‌تر و نزدیک‌تر به لبه‌ها.",
                )
                image = branding.compose_logo_avatar(source, background, padding, color)
            elif image:  # لوگویی که با روش قدیمی (برش از وسط) ذخیره شده و نسخه‌ی اصلی‌اش موجود نیست
                st.warning("برای اینکه کل لوگو دقیق داخل آیکون قرار بگیرد، آن را یک بار دیگر بارگذاری کنید.",
                           icon=":material/upload:")
            else:
                st.caption("هنوز لوگویی بارگذاری نشده است؛ تا آن موقع نشان درخشش نمایش داده می‌شود.")

    if st.button("ذخیره‌ی تغییرات", type="primary", icon=":material/save:", width="stretch"):
        if mode == "image":
            db.set_org_branding(org_id, branding.normalize_color(color), mode, image, source, background, padding)
        else:  # لوگوی قبلی نگه داشته می‌شود تا با برگشت به حالت لوگو دوباره لازم نباشد بارگذاری شود
            db.set_org_branding(org_id, branding.normalize_color(color), mode, saved["image"], saved["source"],
                                saved["background"], saved["padding"])
        st.session_state.pop(BRAND_CACHE, None)  # صفحه‌ی گفتگو فوراً تنظیمات جدید را بگیرد
        st.toast("ظاهر دستیارها به‌روز شد.", icon=":material/check_circle:")

# ---------- پیش‌نمایش زنده ----------
brand = {"color": branding.normalize_color(color), "mode": mode, "image": image}
sample = (db.list_assistants(org_id) or [{"name": "دستیار سازمان"}])[0]["name"]
avatar = chat_style.assistant_avatar(brand, sample)
p = branding.palette(brand["color"])

with preview:
    st.subheader("پیش‌نمایش", icon=":material/visibility:")
    st.html(f"""
<div style="border:1px solid #e8e9f3;border-radius:20px;padding:1.4rem 1.2rem;direction:rtl;
            background:radial-gradient(500px 200px at 50% -60px,{p['glow']},transparent 70%);">
  <div style="text-align:center">
    <img src="{avatar}" alt="" style="width:72px;height:72px;border-radius:24px;
         box-shadow:0 0 0 1px #e8e9f3,0 14px 34px -12px {p['shadow']}">
    <div style="font-weight:700;font-size:1.25rem;margin:.7rem 0 .2rem">سلام! من {html.escape(sample)} هستم</div>
    <span style="font-size:.78rem;color:#059669;background:rgba(16,185,129,.1);padding:.15rem .7rem;
                 border-radius:999px">آنلاین و آماده‌ی پاسخ‌گویی</span>
  </div>
  <div style="display:flex;justify-content:flex-end;margin-top:1.3rem">
    <div style="background:linear-gradient(135deg,{p['brand']},{p['brand-2']});color:{p['on-brand']};
                padding:.6rem 1rem;border-radius:20px;border-end-end-radius:6px;max-width:80%;
                box-shadow:0 10px 24px -14px {p['shadow']}">ساعت کاری شما چیست؟</div>
  </div>
  <div style="display:flex;gap:.6rem;align-items:flex-start;margin-top:.8rem">
    <img src="{avatar}" alt="" style="width:32px;height:32px;border-radius:10px;box-shadow:0 0 0 1px #e8e9f3">
    <div style="border:1px solid #e8e9f3;border-radius:20px;border-start-start-radius:6px;padding:.7rem 1rem;
                background:#fff;flex:1">
      ساعت کاری از شنبه تا چهارشنبه، ۸ تا ۱۶ است [1].
      <div style="margin-top:.5rem"><span style="font-size:.75rem;padding:.1rem .6rem;border-radius:999px;
           background:{p['chip-bg']};color:{p['chip-text']};border:1px solid {p['chip-border']}">آیین‌نامه‌ی داخلی</span></div>
    </div>
  </div>
</div>""")
    st.caption("پیش‌نمایش در حالت روشن است؛ در حالت تیره رنگ‌ها خودکار تنظیم می‌شوند.")

# دکمه‌های رنگ پیشنهادی: هر دکمه با رنگ خودش (کلید هر دکمه کلاس پایدار st-key-preset_... می‌سازد)
st.html("<style>" + "".join(
    f'.st-key-preset_{c.lstrip("#")} button {{ background:{c}; border-color:{c}; width:2.1rem; height:2.1rem; '
    f'min-height:2.1rem; padding:0; border-radius:50%; }}'
    for c in PRESETS
) + "</style>")
