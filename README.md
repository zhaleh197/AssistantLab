---
title: AssistantLab
emoji: 🤖
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Build RAG assistants from your organization's documents
---

# AssistantLab

سامانه‌ای که هر سازمان در آن دستیار هوشمند خودش را می‌سازد: منابع (PDF، Word، اکسل، لینک وب، متن و...) را اضافه می‌کند و اعضای سازمان با دستیار گفتگو می‌کنند. پاسخ‌ها فقط بر پایه‌ی همان منابع و همراه با ارجاع هستند (RAG).

## راه‌اندازی

۱. یک کلید رایگان Gemini از <https://aistudio.google.com/apikey> بگیرید.

۲. فایل `.env.example` را به `.env` کپی کنید و کلید را در `CHAT_API_KEY` بگذارید.

۳. نصب و اجرا (ویندوز):

```bash
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m playwright install chromium-headless-shell
.venv\Scripts\python scripts\check_models.py
.venv\Scripts\streamlit run app.py
```

مرورگر Playwright برای خواندن سایت‌هایی است که محتوایشان را با جاوااسکریپت می‌سازند. اگر درایو C جا ندارد، قبل از دستور نصب `set PLAYWRIGHT_BROWSERS_PATH=%CD%\.playwright` را اجرا کنید؛ برنامه این پوشه را خودش پیدا می‌کند.

اسکریپت `check_models.py` کلید را آزمایش می‌کند و مدل‌های در دسترس را نشان می‌دهد. اگر مدل پیش‌فرض در لیست نبود، `CHAT_MODEL` را در `.env` عوض کنید.

۴. در صفحه‌ی باز شده «ثبت سازمان جدید» را بزنید. سپس دستیار بسازید، منابع اضافه کنید و گفتگو کنید.

## ساختار

| مسیر | کار |
|---|---|
| `app.py` | نقطه‌ی ورود سرور؛ مسیرهای `/auth/finish` و `/auth/logout` برای کوکی ورود |
| `home.py` | صفحه‌ی ورود/ثبت‌نام و منوی صفحه‌ها |
| `views/` | صفحه‌های گفتگو، دستیارها، منابع، اعضا |
| `core/loaders.py` | استخراج متن از فایل‌ها و لینک‌ها (سایت‌های جاوااسکریپتی با مرورگر headless) |
| `core/crawler.py` | خزیدن در صفحه‌های داخلی یک سایت |
| `core/sessions.py` | نشست‌های ماندگار ورود (۳۰ روزه، کوکی HttpOnly) |
| `core/text.py` | یکسان‌سازی فارسی و تکه‌تکه کردن متن |
| `core/ingest.py` | خط لوله‌ی افزودن منبع |
| `core/retrieval.py` | جستجوی ترکیبی معنایی + کلیدواژه‌ای |
| `core/rag.py` | پرامپت، قوانین پاسخ‌دهی و ارجاع‌ها |
| `core/llm.py` | اتصال به مدل (هر API سازگار با OpenAI) |
| `core/db.py` | ذخیره‌سازی (Supabase/Postgres یا SQLite)؛ همه‌ی کوئری‌ها به سازمان محدودند |

## نقش‌ها

- **مدیر**: ساخت دستیار، مدیریت منابع و اعضا، گفتگو
- **عضو**: فقط گفتگو با دستیارهای سازمان

## افزودن یک سایت کامل

در تب «لینک وب»، گزینه‌ی «خزیدن در صفحه‌های داخلی همین سایت» را روشن کنید. از آدرس داده‌شده شروع می‌شود و فقط لینک‌های همان سایت که **زیر همان مسیر** هستند دنبال می‌شوند (مثلاً با `https://site.com/docs/` فقط `/docs/...`). `robots.txt` رعایت می‌شود، صفحه‌های تکراری حذف می‌شوند و هر صفحه در ارجاع‌ها با عنوان و آدرس خودش نشان داده می‌شود. سقف تعداد صفحه با `MAX_CRAWL_PAGES` تنظیم می‌شود (پیش‌فرض ۵۰).

## تعویض مدل

هر سرویس سازگار با OpenAI قابل استفاده است. نمونه‌ی Groq در `.env.example` آمده است. مدل Embedding را بعد از افزودن منابع عوض نکنید، وگرنه منابع باید دوباره اضافه شوند.

## تست

```bash
.venv\Scripts\python -m pytest tests
```

تست‌ها بدون کلید API اجرا می‌شوند (Embedding جعلی).

## دیتابیس: SQLite یا Supabase

- **بدون تنظیم:** SQLite در پوشه‌ی `data` — برای توسعه‌ی محلی.
- **Supabase (برای استفاده‌ی واقعی):** در Supabase یک پروژه بسازید، از دکمه‌ی **Connect** آدرس **Session pooler** (پورت 5432) را بردارید، `[YOUR-PASSWORD]` را با رمز دیتابیس عوض کنید و در `.env` بگذارید:
  ```
  DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
  ```
  جدول‌ها در اولین اجرا خودکار در schema جداگانه‌ی `assistantlab` ساخته می‌شوند. API خودکار Supabase فقط schema `public` را منتشر می‌کند، پس داده‌ها از آن راه قابل دسترسی نیستند. جستجوی معنایی با `pgvector` و جستجوی کلیدواژه‌ای با جستجوی تمام‌متن Postgres انجام می‌شود.

آدرس Transaction pooler (پورت 6543) پشتیبانی نمی‌شود. داده‌های SQLite خودکار منتقل نمی‌شوند؛ منابع را دوباره اضافه کنید.

اجرای تست‌ها روی Postgres واقعی (در یک schema موقت که در پایان حذف می‌شود):
```bash
set TEST_DATABASE_URL=postgresql://...
.venv\Scripts\python -m pytest tests
```

## انتشار روی Hugging Face Spaces

۱. در Hugging Face یک Space بسازید: **SDK: Docker**، قالب **Blank**، سخت‌افزار **CPU basic (رایگان)**.

۲. در **Settings → Variables and secrets** این‌ها را به‌صورت **Secret** اضافه کنید:
   - `CHAT_API_KEY`: کلید Gemini
   - `DATABASE_URL`: آدرس Session pooler سوپابیس

۳. کد را به مخزن Space بفرستید:
```bash
git remote add space https://huggingface.co/spaces/<username>/<space-name>
git push space main
```
برای رمز، یک **Access Token** با دسترسی Write از **Settings → Access Tokens** در Hugging Face بسازید.

۴. ساخت ایمیج چند دقیقه طول می‌کشد. بعد برنامه را از آدرس مستقیم `https://<username>-<space-name>.hf.space` باز کنید، **نه از صفحه‌ی Space در huggingface.co**: آنجا برنامه داخل iframe است و مرورگر کوکی ورود و آپلود فایل را مسدود می‌کند.

نکته‌ها:
- فایل‌های Space عمومی هستند (کد، نه Secretها). اگر Space را Private کنید، فقط اعضای حساب Hugging Face شما می‌توانند برنامه را باز کنند.
- Space رایگان بعد از ۴۸ ساعت بی‌استفاده می‌خوابد و با اولین بازدید دوباره روشن می‌شود (کمتر از یک دقیقه). داده‌ها در Supabase هستند و پاک نمی‌شوند.
- بدون `DATABASE_URL` برنامه با SQLite موقت اجرا می‌شود که با هر ری‌استارت پاک می‌شود.

## محدودیت‌های نسخه‌ی فعلی

- PDFهای اسکن‌شده (تصویری) پشتیبانی نمی‌شوند (OCR ندارد).
- پردازش منابع هم‌زمان با درخواست انجام می‌شود؛ فایل‌های خیلی بزرگ ممکن است چند دقیقه طول بکشند.
- با رفرش صفحه، کاربر وارد می‌ماند ولی تاریخچه‌ی گفتگوی جاری پاک می‌شود.
- سایت‌هایی که مسیریابی‌شان با `#` است (مثل `#/about`) قابل خزیدن نیستند؛ صفحه‌های جاوااسکریپتی هر کدام چند ثانیه طول می‌کشند.
- ورود محدودیت تعداد تلاش ندارد.
- با SQLite جستجو در حافظه انجام می‌شود (مناسب چند ده هزار تکه)؛ با Supabase داخل دیتابیس.
