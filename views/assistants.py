import secrets
from datetime import datetime, timezone

import streamlit as st

from core import db
from core.ui import require_admin, share_link

user = require_admin()
org_id = user["org_id"]

PROMPT_HELP = "نقش، لحن و حوزه‌ی کاری دستیار. مثال: «تو کارشناس پشتیبانی شرکت X هستی؛ کوتاه و صمیمی پاسخ بده.»"

MODE_LABELS = {"sources": "فقط از منابع", "sources_and_general": "منابع + دانش عمومی"}
MODE_CAPTIONS = [
    "فقط از اسناد سازمان و با ارجاع پاسخ می‌دهد؛ اگر جواب در منابع نباشد، همین را می‌گوید. امن‌ترین حالت.",
    "اول از منابع پاسخ می‌دهد؛ برای پرسش‌های عمومی از دانش خودش هم جواب می‌دهد و صریح می‌گوید که از منابع سازمان نیست. "
    "درباره‌ی خود سازمان هرگز حدس نمی‌زند.",
]


STARTERS_HELP = "در صفحه‌ی خوش‌آمد گفتگو به‌صورت دکمه نمایش داده می‌شوند؛ هر خط یک سؤال (حداکثر ۶)."


def answer_mode_input(current: str = "sources", key: str | None = None) -> str:
    return st.radio(
        "نحوه‌ی پاسخ‌دهی", list(MODE_LABELS), index=list(MODE_LABELS).index(current),
        format_func=MODE_LABELS.get, captions=MODE_CAPTIONS, key=key,
    )

st.title("دستیارها", icon=":material/smart_toy:")

with st.expander("ساخت دستیار جدید", expanded=not db.list_assistants(org_id), icon=":material/add_circle:"):
    with st.form("new_assistant", clear_on_submit=True):
        name = st.text_input("نام دستیار", placeholder="مثلاً: دستیار منابع انسانی")
        description = st.text_input("توضیح کوتاه", placeholder="این دستیار به چه سؤال‌هایی پاسخ می‌دهد؟")
        system_prompt = st.text_area("نقش و لحن", help=PROMPT_HELP, height=120)
        starters = st.text_area("سؤال‌های پیشنهادی", help=STARTERS_HELP, height=100,
                                placeholder="مثلاً:\nچه خدماتی ارائه می‌دهید؟\nساعت کاری شما چیست؟")
        answer_mode = answer_mode_input(key="new_answer_mode")
        if st.form_submit_button("ساخت دستیار", type="primary", icon=":material/add:"):
            if not name.strip():
                st.error("نام دستیار را وارد کنید.")
            else:
                st.session_state["selected_assistant"] = db.create_assistant(
                    org_id, name.strip(), description.strip(), system_prompt.strip(), answer_mode, starters.strip()
                )
                st.success("دستیار ساخته شد. حالا از صفحه‌ی «منابع» اسناد آن را اضافه کنید.")
                st.rerun()

assistants = db.list_assistants(org_id)
if not assistants:
    st.info("هنوز دستیاری نساخته‌اید.")

for a in assistants:
    with st.container(border=True):
        st.subheader(a["name"], icon=":material/smart_toy:")
        if a["description"]:
            st.write(a["description"])
        public_label = " · :material/public: لینک عمومی فعال" if a["public_token"] else ""
        st.caption(f"{a['n_sources']} منبع · {a['n_chunks']} تکه‌ی متن · {MODE_LABELS[a['answer_mode']]}{public_label}")

        with st.expander("ویرایش", icon=":material/edit:"):
            with st.form(f"edit_{a['id']}"):
                name = st.text_input("نام دستیار", a["name"])
                description = st.text_input("توضیح کوتاه", a["description"])
                system_prompt = st.text_area("نقش و لحن", a["system_prompt"], help=PROMPT_HELP, height=120)
                starters = st.text_area("سؤال‌های پیشنهادی", a["starter_questions"], help=STARTERS_HELP, height=100)
                answer_mode = answer_mode_input(a["answer_mode"], key=f"answer_mode_{a['id']}")
                if st.form_submit_button("ذخیره", icon=":material/save:"):
                    if name.strip():
                        db.update_assistant(
                            org_id, a["id"], name.strip(), description.strip(), system_prompt.strip(), answer_mode,
                            starters.strip(),
                        )
                        st.rerun()
                    st.error("نام دستیار نمی‌تواند خالی باشد.")

        with st.expander("لینک عمومی", icon=":material/public:"):
            st.caption(
                "با لینک عمومی هر کسی (مثلاً مشتریان سازمان) بدون ورود با این دستیار گفتگو می‌کند. "
                "بازدیدکنندگان نام منابع را می‌بینند ولی متن داخلی اسناد به آن‌ها نمایش داده نمی‌شود."
            )
            if a["public_token"]:
                st.code(share_link(a=a["public_token"]), language=None)
                today = datetime.now(timezone.utc).date().isoformat()
                used = db.public_usage_today(a["id"], today)  # درخواست‌های ردشده بعد از سقف هم شمرده می‌شوند
                limit_now = a["public_daily_limit"]
                full = " — سقف امروز پر شده است" if used >= limit_now else ""
                st.caption(f"سؤال‌های امروز: {min(used, limit_now)} از {limit_now}{full}")
                with st.form(f"public_limit_{a['id']}"):
                    limit = st.number_input(
                        "سقف سؤال در روز", min_value=1, max_value=10000, value=int(a["public_daily_limit"]),
                        help="از سهمیه‌ی سرویس‌های مدل زبانی محافظت می‌کند؛ بعد از رسیدن به سقف تا فردا پاسخی داده نمی‌شود.",
                    )
                    if st.form_submit_button("ذخیره‌ی سقف"):
                        db.set_public_link(org_id, a["id"], a["public_token"], int(limit))
                        st.rerun()
                cols = st.columns(2)
                if cols[0].button("ساخت لینک جدید", key=f"regen_{a['id']}",
                                  help="لینک فعلی دیگر کار نمی‌کند."):
                    db.set_public_link(org_id, a["id"], secrets.token_urlsafe(16))
                    st.rerun()
                if cols[1].button("خاموش کردن لینک", key=f"disable_{a['id']}"):
                    db.set_public_link(org_id, a["id"], None)
                    st.rerun()
            elif st.button("فعال کردن لینک عمومی", key=f"enable_{a['id']}", type="primary"):
                db.set_public_link(org_id, a["id"], secrets.token_urlsafe(16))
                st.rerun()

        with st.expander("حذف", icon=":material/delete:"):
            st.warning("با حذف دستیار، همه‌ی منابع آن هم حذف می‌شود.")
            confirm = st.checkbox("مطمئنم", key=f"confirm_del_{a['id']}")
            if st.button("حذف دستیار", key=f"del_{a['id']}", disabled=not confirm):
                db.delete_assistant(org_id, a["id"])
                st.rerun()
