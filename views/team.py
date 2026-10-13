import streamlit as st

from core import auth, db
from core.ui import require_admin, share_link

user = require_admin()
org_id = user["org_id"]

ROLE_LABELS = {"admin": "مدیر", "member": "عضو"}

st.title("اعضای سازمان")

org = db.get_org(org_id)
with st.container(border=True):
    st.subheader("آدرس ورود سازمان")
    if org["slug"]:
        st.caption("این آدرس را به اعضای سازمان بدهید؛ صفحه‌ی ورود با نام سازمان شما باز می‌شود "
                   "و فقط اعضای همین سازمان می‌توانند وارد شوند.")
        st.code(share_link(org=org["slug"]), language=None)
    else:
        st.caption("هنوز آدرسی برای سازمان تعیین نکرده‌اید.")
    with st.form("org_slug"):
        slug = st.text_input("آدرس سازمان (انگلیسی)", value=org["slug"] or "", placeholder="مثلاً akam")
        if org["slug"]:
            st.caption("با تغییر آدرس، آدرس قبلی دیگر کار نمی‌کند.")
        if st.form_submit_button("ذخیره‌ی آدرس"):
            slug = slug.strip().lower()
            error = auth.validate_slug(slug)
            if error:
                st.error(error)
            elif slug != org["slug"]:
                try:
                    db.set_org_slug(org_id, slug)
                    st.rerun()
                except db.DuplicateError as e:
                    st.error(str(e))

st.caption("«عضو» فقط می‌تواند با دستیارها گفتگو کند؛ «مدیر» دستیار و منابع را هم مدیریت می‌کند.")

with st.expander("➕ افزودن عضو"):
    with st.form("new_member", clear_on_submit=True):
        display_name = st.text_input("نام")
        username = st.text_input("نام کاربری (انگلیسی)")
        password = st.text_input("رمز عبور اولیه", type="password")
        role = st.selectbox("نقش", ["member", "admin"], format_func=ROLE_LABELS.get)
        if st.form_submit_button("افزودن", type="primary"):
            username = username.strip()
            error = auth.validate_new_account(username, password)
            if not display_name.strip():
                error = "نام را وارد کنید."
            if error:
                st.error(error)
            else:
                try:
                    db.create_user(org_id, username, display_name.strip(), auth.hash_password(password), role)
                    st.success(f"«{display_name}» اضافه شد. نام کاربری و رمز را به او بدهید.")
                except db.DuplicateError as e:
                    st.error(str(e))

for m in db.list_users(org_id):
    cols = st.columns([4, 3, 2, 1])
    cols[0].markdown(f"**{m['display_name']}**")
    cols[1].code(m["username"], language=None)
    cols[2].write(ROLE_LABELS[m["role"]])
    if m["id"] != user["id"] and cols[3].button("🗑️", key=f"del_user_{m['id']}", help="حذف عضو"):
        db.delete_user(org_id, m["id"])
        st.rerun()
