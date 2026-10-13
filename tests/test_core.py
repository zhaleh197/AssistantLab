import hashlib
import io
import os
import secrets
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import auth, db, ingest, llm, loaders, rag, retrieval  # noqa: E402
from core.text import chunk_text, clean, tokenize  # noqa: E402


# برای اجرای تست‌ها روی Postgres واقعی (مثلاً Supabase) این متغیر را تنظیم کنید؛
# تست‌ها در یک schema موقت اجرا می‌شوند که در پایان حذف می‌شود.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
FAKE_DIMS = 64


def fake_embed(texts):
    """Embedding جعلی بر پایه‌ی کلمات، تا تست‌ها بدون API اجرا شوند."""
    out = np.zeros((len(texts), FAKE_DIMS), dtype=np.float32)
    for i, t in enumerate(texts):
        for tok in tokenize(t):
            out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % FAKE_DIMS] += 1
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


@pytest.fixture(scope="session")
def pg_schema():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL تنظیم نشده است")
    import psycopg

    schema = f"assistantlab_test_{secrets.token_hex(4)}"
    yield schema
    db.reset()
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True, prepare_threshold=None) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


@pytest.fixture(autouse=True, params=["sqlite", "postgres"])
def backend(request, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "embed", fake_embed)
    monkeypatch.setattr(db, "EMBED_DIMS", FAKE_DIMS)
    if request.param == "sqlite":
        monkeypatch.setattr(db, "DATABASE_URL", "")
        monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
        db.init_db()
    else:
        monkeypatch.setattr(db, "DATABASE_URL", TEST_DATABASE_URL)
        monkeypatch.setattr(db, "PG_SCHEMA", request.getfixturevalue("pg_schema"))
        db.init_db()
        with db.connect() as c:
            c.execute("TRUNCATE organizations, auth_tokens RESTART IDENTITY CASCADE")
    return request.param


def make_org(name="org", username="admin1"):
    return db.create_org_with_admin(name, username, "Admin", auth.hash_password("password123"))


# ---------- متن ----------

def test_clean_normalizes_arabic_chars_and_digits():
    assert clean("كتاب علي ۱۲۳") == "کتاب علی 123"


def test_tokenize_joins_zwnj():
    assert tokenize("می‌روم") == tokenize("میروم") == ["میروم"]


def test_chunk_respects_size_and_keeps_all_text():
    paras = [f"پاراگراف شماره {i} " + "کلمه " * 40 for i in range(20)]
    chunks = chunk_text("\n\n".join(paras), size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 + 60 for c in chunks)
    for i in range(20):
        assert any(f"پاراگراف شماره {i} " in c for c in chunks)


def test_chunk_splits_one_giant_paragraph():
    chunks = chunk_text("واژه " * 2000, size=300, overlap=0)
    assert len(chunks) > 10 and all(len(c) <= 300 for c in chunks)


# ---------- احراز هویت ----------

def test_password_hash_roundtrip():
    h = auth.hash_password("secret-pass")
    assert auth.verify_password("secret-pass", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "garbage")


def test_validate_new_account():
    assert auth.validate_new_account("ab", "password123")
    assert auth.validate_new_account("good_name", "short")
    assert auth.validate_new_account("good_name", "password123") is None


# ---------- بارگذاری فایل ----------

def test_extract_docx_and_csv():
    import docx

    d = docx.Document()
    d.add_paragraph("سیاست مرخصی شرکت")
    buf = io.BytesIO()
    d.save(buf)
    assert "مرخصی" in loaders.extract_file("a.docx", buf.getvalue())[0][1]

    csv = "نام,سمت\nعلی,مدیر\n".encode("utf-8")
    assert "سمت: مدیر" in loaders.extract_file("a.csv", csv)[0][1]


def test_extract_rejects_unknown_format():
    with pytest.raises(loaders.UnsupportedSource):
        loaders.extract_file("a.exe", b"xx")


class _FakeResponse:
    is_redirect = False
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __init__(self, body: bytes):
        self.body = body

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.body


def test_js_rendered_page_falls_back_to_browser(monkeypatch):
    shell = b"<html><head><title>Shell</title><meta name='description' content='desc'></head>" \
            b"<body><main><h1></h1><div id='root'></div></main></body></html>"
    rendered = ("<html><body><main>" + "<p>محتوای واقعی سایت</p>" * 30 + "</main></body></html>").encode()

    monkeypatch.setattr(loaders, "_assert_public_host", lambda url: None)
    monkeypatch.setattr(loaders.requests, "get", lambda *a, **k: _FakeResponse(shell))
    monkeypatch.setattr(loaders, "_render_with_browser", lambda url: rendered)

    title, segs = loaders.extract_url("https://spa.example/")
    assert title == "Shell"
    assert "desc" in segs[0][1] and "محتوای واقعی سایت" in segs[0][1]


def test_static_page_does_not_use_browser(monkeypatch):
    page = ("<html><body><article>" + "<p>متن کامل صفحه</p>" * 40 + "</article></body></html>").encode()

    def no_browser(url):
        raise AssertionError("browser should not be used")

    monkeypatch.setattr(loaders, "_assert_public_host", lambda url: None)
    monkeypatch.setattr(loaders.requests, "get", lambda *a, **k: _FakeResponse(page))
    monkeypatch.setattr(loaders, "_render_with_browser", no_browser)
    assert "متن کامل صفحه" in loaders.extract_url("https://static.example/")[1][0][1]


def test_url_blocks_private_hosts():
    for url in ("http://127.0.0.1/admin", "http://169.254.169.254/latest", "file:///etc/passwd"):
        with pytest.raises(loaders.UnsupportedSource):
            loaders.extract_url(url)


# ---------- ingest و جستجو ----------

def test_ingest_and_hybrid_search():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "HR", "", "")
    ingest.ingest(org["org_id"], aid, "text", "مرخصی", [("", "کارمندان سالانه ۲۶ روز مرخصی استحقاقی دارند.")])
    ingest.ingest(org["org_id"], aid, "text", "حقوق", [("", "حقوق ماهانه روز پنجم هر ماه واریز می‌شود.")])

    hits = retrieval.search(org["org_id"], aid, "چند روز مرخصی داریم؟", k=2)
    assert hits[0].source_name == "مرخصی"


def test_tenant_isolation():
    a = make_org("A", "admin_a")
    b = make_org("B", "admin_b")
    aid = db.create_assistant(a["org_id"], "secret", "", "")
    ingest.ingest(a["org_id"], aid, "text", "محرمانه", [("", "رمز گاوصندوق ۱۲۳۴ است")])

    # سازمان B با شناسه‌ی دستیار A هیچ چیزی نمی‌بیند و نمی‌تواند حذفش کند
    assert retrieval.search(b["org_id"], aid, "رمز گاوصندوق", k=5) == []
    assert db.get_assistant(b["org_id"], aid) is None
    db.delete_assistant(b["org_id"], aid)
    assert db.get_assistant(a["org_id"], aid) is not None


def test_ingest_failure_marks_source_error(monkeypatch):
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    with pytest.raises(ValueError):
        ingest.ingest(org["org_id"], aid, "text", "خالی", [("", "   ")])
    assert db.list_sources(org["org_id"], aid)[0]["status"] == "error"


def test_quota(monkeypatch):
    monkeypatch.setattr(ingest.config, "MAX_CHUNKS_PER_ORG", 1)
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    with pytest.raises(ingest.QuotaExceeded):
        ingest.ingest(org["org_id"], aid, "text", "big", [("", "\n\n".join(["متن " * 300] * 3))])


def test_deleting_source_updates_search_index():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    ingest.ingest(org["org_id"], aid, "text", "s1", [("", "قانون کار")])
    assert retrieval.search(org["org_id"], aid, "قانون", k=3)
    db.delete_source(org["org_id"], db.list_sources(org["org_id"], aid)[0]["id"])
    assert retrieval.search(org["org_id"], aid, "قانون", k=3) == []


# ---------- پرامپت و ارجاع ----------

def test_cited_numbers():
    assert rag.cited_numbers("الف [2] ب [۱][2] ج [9]", n_hits=3) == [2, 1]
    assert rag.cited_numbers("رتبه سوم【1】 و【3】", n_hits=3) == [1, 3]


def test_build_messages_contains_sources_and_persona():
    hit = retrieval.Hit(1, 1, "دفترچه", "صفحه 3", "متن نمونه", 1.0)
    msgs = rag.build_messages({"name": "دستیار", "system_prompt": "لحن صمیمی"}, [], "سؤال؟", [hit])
    assert "لحن صمیمی" in msgs[0]["content"]
    assert "[1] (دفترچه — صفحه 3)" in msgs[-1]["content"]


# ---------- ورود ماندگار ----------

def test_session_identifies_user_without_password_hash():
    from core import sessions

    user = make_org()
    token = sessions.create_session(user["id"])
    found = sessions.user_for_session(token)
    assert found["id"] == user["id"] and found["org_name"] == "org"
    assert "password_hash" not in found


def test_expired_and_revoked_sessions_are_rejected(monkeypatch):
    from core import sessions

    user = make_org()
    monkeypatch.setattr(sessions, "SESSION_TTL", -1)
    assert sessions.user_for_session(sessions.create_session(user["id"])) is None

    monkeypatch.setattr(sessions, "SESSION_TTL", 3600)
    token = sessions.create_session(user["id"])
    sessions.revoke(token)
    assert sessions.user_for_session(token) is None
    assert sessions.user_for_session("") is None and sessions.user_for_session("garbage") is None


def test_deleting_user_ends_their_sessions():
    from core import sessions

    admin = make_org()
    db.create_user(admin["org_id"], "member1", "M", auth.hash_password("password123"), "member")
    member = db.get_user_by_username("member1")
    token = sessions.create_session(member["id"])
    db.delete_user(admin["org_id"], member["id"])
    assert sessions.user_for_session(token) is None


# ---------- خزیدن ----------

def _fake_site(monkeypatch, pages: dict[str, tuple[str, list[str]]]):
    """pages: url -> (text, links)"""
    from core import crawler

    def load_page(url):
        if url not in pages:
            raise loaders.UnsupportedSource("404")
        text, links = pages[url]
        return loaders.WebPage(url, f"T:{url.rsplit('/', 1)[-1] or 'home'}", [("", text)], links)

    monkeypatch.setattr(crawler.loaders, "load_page", load_page)
    monkeypatch.setattr(crawler.loaders, "_assert_public_host", lambda url: None)
    monkeypatch.setattr(crawler, "_robots", lambda url: None)
    monkeypatch.setattr(crawler, "REQUEST_DELAY", 0)
    return crawler


def test_crawl_follows_internal_links_only(monkeypatch):
    crawler = _fake_site(monkeypatch, {
        "https://site.com/docs/": ("صفحه اصلی", [
            "https://site.com/docs/a", "https://site.com/docs/a#bottom", "https://site.com/docs/index.html",
            "https://other.com/x", "https://site.com/blog/post", "https://site.com/docs/logo.png",
            "mailto:me@site.com",
        ]),
        "https://site.com/docs/a": ("صفحه الف", ["https://site.com/docs/b", "https://site.com/docs/"]),
        "https://site.com/docs/b": ("صفحه ب", []),
    })
    result = crawler.crawl("https://site.com/docs/", max_pages=10)
    assert result.pages == ["https://site.com/docs/", "https://site.com/docs/a", "https://site.com/docs/b"]
    assert "(https://site.com/docs/a)" in result.segments[1][0]
    assert not result.failures


def test_crawl_respects_page_limit_skips_duplicates_and_reports_failures(monkeypatch):
    crawler = _fake_site(monkeypatch, {
        "https://site.com/": ("خانه", ["https://site.com/1", "https://site.com/dup", "https://site.com/broken",
                                        "https://site.com/2", "https://site.com/3"]),
        "https://site.com/1": ("یک", []),
        "https://site.com/dup": ("خانه", []),
        "https://site.com/2": ("دو", []),
        "https://site.com/3": ("سه", []),
    })
    result = crawler.crawl("https://site.com/", max_pages=3)
    assert result.pages == ["https://site.com/", "https://site.com/1", "https://site.com/2"]
    assert [u for u, _ in result.failures] == ["https://site.com/broken"]


def test_crawl_with_no_readable_page_raises(monkeypatch):
    crawler = _fake_site(monkeypatch, {})
    with pytest.raises(loaders.UnsupportedSource):
        crawler.crawl("https://site.com/", max_pages=5)


def test_keyword_search_matches_persian_regardless_of_zwnj():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    ingest.ingest(org["org_id"], aid, "text", "قوانین", [("", "کارمندان می‌توانند دورکاری کنند.")])
    ingest.ingest(org["org_id"], aid, "text", "دیگر", [("", "ساعت کاری از هشت صبح است.")])
    assert retrieval.search(org["org_id"], aid, "میتوانند", k=1)[0].source_name == "قوانین"


def test_duplicate_username_raises_duplicate_error():
    org = make_org()
    with pytest.raises(db.DuplicateError):
        db.create_user(org["org_id"], "admin1", "x", auth.hash_password("password123"), "member")
    with pytest.raises(db.DuplicateError):
        make_org("other", "admin1")


def test_rejects_transaction_pooler_url(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@aws-0-x.pooler.supabase.com:6543/postgres")
    with pytest.raises(db.ConfigError):
        db._validate_pg_config()


def _fake_chat(monkeypatch, behaviour, models, keys=None):
    """behaviour: model -> 'busy' (خطا قبل از شروع) | 'gone' (مدل بازنشسته) | 'cut' (خطا وسط پاسخ) | متن پاسخ.
    models: مقدار CHAT_MODELS. فراخوانی‌ها به‌صورت (base_url, api_key, model, reasoning_effort) ثبت می‌شوند."""
    import httpx2 as httpx
    from types import SimpleNamespace
    from openai import APITimeoutError, NotFoundError

    calls = []

    def chunk(text):
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

    def make_client(base_url, api_key):
        def create(model, **kwargs):
            calls.append((base_url, api_key, model, kwargs.get("reasoning_effort")))
            mode = behaviour[model]
            request = httpx.Request("POST", "https://x")
            if mode == "busy":
                raise APITimeoutError(request=request)
            if mode == "gone":
                raise NotFoundError("gone", response=httpx.Response(404, request=request), body=None)
            if mode == "cut":
                def gen():
                    yield chunk("نیمه")
                    raise APITimeoutError(request=request)
                return gen()
            return [chunk(mode)]

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client.with_options = lambda **kw: client
        return client

    monkeypatch.setattr(llm, "_client", make_client)
    monkeypatch.setattr(llm.config, "CHAT_MODELS", models)
    monkeypatch.setattr(llm.config, "PROVIDER_KEYS", keys or {"gemini": "gemini-key", "groq": "groq-key"})
    monkeypatch.setattr(llm.config, "GEMINI_REASONING_EFFORT", "minimal")
    return calls


def test_stream_chat_falls_back_when_primary_model_is_busy(monkeypatch):
    calls = _fake_chat(monkeypatch, {"primary": "busy", "backup": "سلام"}, "groq:primary, groq:backup")
    assert "".join(llm.stream_chat([])) == "سلام"
    assert [c[2] for c in calls] == ["primary", "backup"]


def test_fallback_across_providers_uses_each_providers_key(monkeypatch):
    calls = _fake_chat(monkeypatch, {"qwen-x": "busy", "gemini-y": "پاسخ"}, "groq:qwen-x, gemini:gemini-y")
    assert "".join(llm.stream_chat([])) == "پاسخ"
    groq, gemini = calls
    assert groq[:2] == ("https://api.groq.com/openai/v1", "groq-key") and groq[3] is None
    assert gemini[1] == "gemini-key" and gemini[3] == "minimal"   # فکر کردن حداقلی فقط برای Gemini


def test_retired_model_is_skipped(monkeypatch):
    calls = _fake_chat(monkeypatch, {"old": "gone", "new": "تازه"}, "groq:old, groq:new")
    assert "".join(llm.stream_chat([])) == "تازه"
    assert [c[2] for c in calls] == ["old", "new"]


def test_models_without_key_or_unknown_provider_are_ignored(monkeypatch):
    _fake_chat(monkeypatch, {}, "groq:a, nowhere:b, gemini:c, bad-entry", keys={"gemini": "k", "groq": ""})
    assert [str(t) for t in llm.chat_targets()] == ["gemini:c"]
    monkeypatch.setattr(llm.config, "PROVIDER_KEYS", {"gemini": "", "groq": ""})
    with pytest.raises(llm.MissingApiKey):
        llm.chat_targets()


def test_error_mid_answer_is_not_retried_with_another_model(monkeypatch):
    calls = _fake_chat(monkeypatch, {"primary": "cut", "backup": "کامل"}, "groq:primary, groq:backup")
    out = []
    with pytest.raises(llm.TRANSIENT_ERRORS):
        for piece in llm.stream_chat([]):
            out.append(piece)
    assert out == ["نیمه"] and [c[2] for c in calls] == ["primary"]


def test_small_talk_detection():
    assert rag.is_small_talk("سلام") and rag.is_small_talk("سلام خوبی؟") and rag.is_small_talk("خیلی ممنون")
    assert not rag.is_small_talk("سلام، قیمت خدمات چقدر است؟")
    assert not rag.is_small_talk("اعضای تیم چه کسانی هستند؟")


def test_add_chunks_is_idempotent_for_retries():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    sid = db.create_source(org["org_id"], aid, "text", "s", "m")
    items = [("", "متن یک"), ("", "متن دو")]
    db.add_chunks(org["org_id"], aid, sid, items, fake_embed([t for _, t in items]))
    db.add_chunks(org["org_id"], aid, sid, items, fake_embed([t for _, t in items]))  # تلاش دوباره
    assert db.count_org_chunks(org["org_id"]) == 2


# ---------- حالت پاسخ‌دهی ----------

def test_answer_mode_defaults_to_sources_and_can_be_changed():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "a", "", "")
    assert db.get_assistant(org["org_id"], aid)["answer_mode"] == "sources"
    db.update_assistant(org["org_id"], aid, "a", "", "", "sources_and_general")
    assert db.get_assistant(org["org_id"], aid)["answer_mode"] == "sources_and_general"


def test_old_sqlite_database_gets_answer_mode_column(tmp_path, monkeypatch, backend):
    if backend != "sqlite":
        pytest.skip("مهاجرت SQLite")
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SQLITE_SCHEMA.replace(
        "    answer_mode TEXT NOT NULL DEFAULT 'sources' CHECK (answer_mode IN ('sources', 'sources_and_general')),\n", ""
    ))
    old.execute("INSERT INTO organizations (name) VALUES ('o')")
    old.execute("INSERT INTO assistants (org_id, name) VALUES (1, 'قدیمی')")
    old.commit()
    old.close()

    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    migrated = db.get_assistant(1, 1)
    assert migrated["answer_mode"] == "sources"
    assert migrated["public_token"] is None and migrated["public_daily_limit"] == 200
    assert db.get_org(1)["slug"] is None


def test_rules_follow_answer_mode():
    strict = rag.build_messages({"name": "x", "answer_mode": "sources"}, [], "q", [])[0]["content"]
    general = rag.build_messages({"name": "x", "answer_mode": "sources_and_general"}, [], "q", [])[0]["content"]
    assert "از دانش عمومی خودت چیزی اضافه نکن" in strict and rag.GENERAL_PREFIX not in strict
    assert rag.GENERAL_PREFIX in general and "حدس نزن" in general
    for rules in (strict, general):
        assert "نام مدل زبانی یا شرکت سازنده‌ی آن را نگو" in rules



# ---------- آدرس سازمان ----------

def test_org_slug_is_unique_and_resolvable():
    a = db.create_org_with_admin("اکام", "admin_a", "A", auth.hash_password("password123"), "akam")
    assert db.get_org_by_slug("akam")["id"] == a["org_id"]
    with pytest.raises(db.DuplicateError):
        db.create_org_with_admin("دیگر", "admin_b", "B", auth.hash_password("password123"), "akam")
    b = make_org("بی", "admin_c")                     # سازمان بدون آدرس (ثبت‌شده‌ی قدیمی)
    with pytest.raises(db.DuplicateError):
        db.set_org_slug(b["org_id"], "akam")
    db.set_org_slug(b["org_id"], "bee")
    assert db.get_org_by_slug("bee")["id"] == b["org_id"] and db.get_org_by_slug("nope") is None


def test_validate_slug():
    assert auth.validate_slug("akam") is None and auth.validate_slug("my-org-2") is None
    for bad in ("ak", "Akam", "-akam", "akam-", "اکام", "a b c", "x" * 31):
        assert auth.validate_slug(bad)


# ---------- لینک عمومی ----------

def test_public_link_enable_regenerate_disable():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "عمومی", "", "")
    assert db.get_public_assistant("anything") is None and db.get_public_assistant("") is None

    db.set_public_link(org["org_id"], aid, "token-1", 50)
    found = db.get_public_assistant("token-1")
    assert found["id"] == aid and found["org_name"] == "org" and found["public_daily_limit"] == 50

    db.set_public_link(org["org_id"], aid, "token-2")         # لینک جدید، لینک قبلی باطل
    assert db.get_public_assistant("token-1") is None and db.get_public_assistant("token-2")["id"] == aid
    assert db.get_public_assistant("token-2")["public_daily_limit"] == 50

    db.set_public_link(org["org_id"], aid, None)              # خاموش
    assert db.get_public_assistant("token-2") is None


def test_public_link_of_another_org_cannot_be_changed():
    a = make_org("A", "admin_a")
    b = make_org("B", "admin_b")
    aid = db.create_assistant(a["org_id"], "x", "", "")
    db.set_public_link(b["org_id"], aid, "hijack")
    assert db.get_public_assistant("hijack") is None


def test_public_usage_counts_per_day_and_is_removed_with_assistant():
    org = make_org()
    aid = db.create_assistant(org["org_id"], "x", "", "")
    assert [db.count_public_question(aid, "2026-10-14") for _ in range(3)] == [1, 2, 3]
    assert db.count_public_question(aid, "2026-10-15") == 1
    assert db.public_usage_today(aid, "2026-10-14") == 3 and db.public_usage_today(aid, "2026-01-01") == 0
    db.delete_assistant(org["org_id"], aid)
    assert db.public_usage_today(aid, "2026-10-14") == 0
