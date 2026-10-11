import streamlit as st

from core import db
from core.ui import require_admin

user = require_admin()
org_id = user["org_id"]

PROMPT_HELP = "نقش، لحن و حوزه‌ی کاری دستیار. مثال: «تو کارشناس پشتیبانی شرکت X هستی؛ کوتاه و صمیمی پاسخ بده.»"

st.title("دستیارها")

with st.expander("➕ ساخت دستیار جدید", expanded=not db.list_assistants(org_id)):
    with st.form("new_assistant", clear_on_submit=True):
        name = st.text_input("نام دستیار", placeholder="مثلاً: دستیار منابع انسانی")
        description = st.text_input("توضیح کوتاه", placeholder="این دستیار به چه سؤال‌هایی پاسخ می‌دهد؟")
        system_prompt = st.text_area("نقش و لحن", help=PROMPT_HELP, height=120)
        if st.form_submit_button("ساخت دستیار", type="primary"):
            if not name.strip():
                st.error("نام دستیار را وارد کنید.")
            else:
                st.session_state["selected_assistant"] = db.create_assistant(
                    org_id, name.strip(), description.strip(), system_prompt.strip()
                )
                st.success("دستیار ساخته شد. حالا از صفحه‌ی «منابع» اسناد آن را اضافه کنید.")
                st.rerun()

assistants = db.list_assistants(org_id)
if not assistants:
    st.info("هنوز دستیاری نساخته‌اید.")

for a in assistants:
    with st.container(border=True):
        st.subheader(a["name"])
        if a["description"]:
            st.write(a["description"])
        st.caption(f"{a['n_sources']} منبع · {a['n_chunks']} تکه‌ی متن")

        with st.expander("ویرایش"):
            with st.form(f"edit_{a['id']}"):
                name = st.text_input("نام دستیار", a["name"])
                description = st.text_input("توضیح کوتاه", a["description"])
                system_prompt = st.text_area("نقش و لحن", a["system_prompt"], help=PROMPT_HELP, height=120)
                if st.form_submit_button("ذخیره"):
                    if name.strip():
                        db.update_assistant(org_id, a["id"], name.strip(), description.strip(), system_prompt.strip())
                        st.rerun()
                    st.error("نام دستیار نمی‌تواند خالی باشد.")

        with st.expander("حذف"):
            st.warning("با حذف دستیار، همه‌ی منابع آن هم حذف می‌شود.")
            confirm = st.checkbox("مطمئنم", key=f"confirm_del_{a['id']}")
            if st.button("حذف دستیار", key=f"del_{a['id']}", disabled=not confirm):
                db.delete_assistant(org_id, a["id"])
                st.rerun()
