import streamlit as st

import config
from core import crawler, db, loaders
from core.ingest import ingest
from core.ui import pick_assistant, require_admin

user = require_admin()
org_id = user["org_id"]

STATUS_LABELS = {"processing": "⏳ در حال پردازش", "ready": "✅ آماده", "error": "❌ خطا"}
KIND_LABELS = {"file": "فایل", "url": "لینک", "text": "متن"}

st.title("منابع دانش")

assistant = pick_assistant(db.list_assistants(org_id), key="sources_assistant")
if not assistant:
    st.info("ابتدا از صفحه‌ی «دستیارها» یک دستیار بسازید.")
    st.stop()


def run_ingest(kind: str, name: str, extract) -> None:
    """extract(status) باید (name, segments) برگرداند؛ خطاها به‌صورت پیام نمایش داده می‌شوند."""
    with st.status(f"در حال پردازش «{name}»...") as status:
        try:
            final_name, segments = extract(status)
            n = ingest(org_id, assistant["id"], kind, final_name, segments)
            status.update(label=f"«{final_name}» اضافه شد ({n} تکه).", state="complete")
        except Exception as e:  # خطا به کاربر نمایش داده می‌شود و در وضعیت منبع هم ثبت شده
            status.update(label=f"خطا در «{name}»", state="error")
            st.error(str(e))


tab_files, tab_url, tab_text = st.tabs(["📄 فایل", "🔗 لینک وب", "📝 متن"])

with tab_files:
    st.caption("فرمت‌های پشتیبانی‌شده: " + "، ".join(loaders.SUPPORTED_EXTS))
    with st.form("upload", clear_on_submit=True):
        files = st.file_uploader("فایل‌ها را انتخاب کنید", accept_multiple_files=True)
        submitted = st.form_submit_button("افزودن", type="primary")
    if submitted and files:
        for f in files:
            data = f.getvalue()
            run_ingest("file", f.name, lambda _, f=f, data=data: (f.name, loaders.extract_file(f.name, data)))


def crawl_site(status, url: str, max_pages: int):
    def on_page(i: int, page_url: str) -> None:
        status.update(label=f"در حال خواندن صفحه‌ی {i} از حداکثر {max_pages}...")
        st.write(f"`{page_url}`")

    result = crawler.crawl(url, max_pages, on_page)
    if result.failures:
        st.warning(f"{len(result.failures)} صفحه خوانده نشد:\n\n" +
                   "\n".join(f"- `{u}`: {err}" for u, err in result.failures[:10]))
    return f"{result.title or url} ({len(result.pages)} صفحه)", result.segments


with tab_url:
    with st.form("url", clear_on_submit=True):
        url = st.text_input("آدرس صفحه", placeholder="https://example.com/page")
        do_crawl = st.toggle("خزیدن در صفحه‌های داخلی همین سایت",
                             help="لینک‌های همان سایت که زیر همین آدرس هستند هم خوانده می‌شوند.")
        max_pages = st.number_input("حداکثر تعداد صفحه", min_value=2, max_value=config.MAX_CRAWL_PAGES,
                                    value=min(20, config.MAX_CRAWL_PAGES))
        submitted = st.form_submit_button("افزودن", type="primary")
    if submitted and url.strip():
        if do_crawl:
            run_ingest("url", url.strip(), lambda status: crawl_site(status, url.strip(), int(max_pages)))
        else:
            run_ingest("url", url.strip(), lambda _: loaders.extract_url(url))

with tab_text:
    with st.form("text", clear_on_submit=True):
        title = st.text_input("عنوان")
        body = st.text_area("متن", height=200)
        submitted = st.form_submit_button("افزودن", type="primary")
    if submitted:
        if not title.strip() or not body.strip():
            st.error("عنوان و متن را وارد کنید.")
        else:
            run_ingest("text", title.strip(), lambda _: (title.strip(), [("", body)]))

st.divider()
sources = db.list_sources(org_id, assistant["id"])
st.subheader(f"منابع «{assistant['name']}» ({len(sources)})")
if not sources:
    st.info("هنوز منبعی اضافه نشده است.")

for s in sources:
    cols = st.columns([5, 2, 2, 1])
    cols[0].markdown(f"**{s['name']}**  \n{KIND_LABELS[s['kind']]} · {s['created_at'][:16]}")
    cols[1].write(STATUS_LABELS[s["status"]])
    cols[2].write(f"{s['n_chunks']} تکه" if s["status"] == "ready" else "")
    if cols[3].button("🗑️", key=f"del_src_{s['id']}", help="حذف منبع"):
        db.delete_source(org_id, s["id"])
        st.rerun()
    if s["status"] == "error" and s["error"]:
        st.caption(f"⚠️ {s['error']}")
