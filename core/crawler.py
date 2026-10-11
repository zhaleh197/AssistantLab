"""خزیدن در صفحه‌های یک سایت: از آدرس شروع، لینک‌های داخلی همان سایت (و زیر همان مسیر) دنبال می‌شوند."""
import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import requests

from core import loaders
from core.text import clean

Segments = list[tuple[str, str]]

# پسوندهایی که صفحه‌ی متنی نیستند و دنبال نمی‌شوند
SKIP_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm", ".mkv",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".exe", ".msi", ".dmg", ".apk", ".iso",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot",
}
REQUEST_DELAY = 0.3


@dataclass
class CrawlResult:
    title: str
    segments: Segments
    pages: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)


def normalize(url: str) -> str:
    url, _ = urldefrag(url.strip())
    p = urlparse(url)
    path = p.path or "/"
    for index in ("index.html", "index.htm"):
        if path.endswith("/" + index):
            path = path[: -len(index)]
    return p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower(), path=path).geturl()


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _scope_prefix(start_url: str) -> str:
    """فقط صفحه‌های زیر پوشه‌ی آدرس شروع خزیده می‌شوند (مثلاً /docs/ ← فقط /docs/...)."""
    path = urlparse(start_url).path or "/"
    return path if path.endswith("/") else path.rsplit("/", 1)[0] + "/"


def in_scope(url: str, start_url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or _host(url) != _host(start_url):
        return False
    if PurePosixPath(p.path).suffix.lower() in SKIP_EXTS:
        return False
    return (p.path or "/").startswith(_scope_prefix(start_url))


def _robots(start_url: str) -> RobotFileParser | None:
    p = urlparse(start_url)
    try:
        resp = requests.get(f"{p.scheme}://{p.netloc}/robots.txt",
                            headers={"User-Agent": loaders.USER_AGENT}, timeout=10)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    rp = RobotFileParser()
    rp.parse(resp.text.splitlines())
    return rp


def crawl(start_url: str, max_pages: int,
          on_page: Callable[[int, str], None] | None = None) -> CrawlResult:
    start_url = normalize(start_url)
    loaders._assert_public_host(start_url)
    robots = _robots(start_url)

    queue = deque([start_url])
    seen = {start_url}
    seen_content: set[str] = set()
    result = CrawlResult(title="", segments=[])

    while queue and len(result.pages) < max_pages:
        url = queue.popleft()
        if robots and not robots.can_fetch(loaders.USER_AGENT, url):
            continue
        if on_page:
            on_page(len(result.pages) + 1, url)
        try:
            page = loaders.load_page(url)
        except Exception as e:  # خطای یک صفحه نباید کل خزیدن را متوقف کند
            result.failures.append((url, str(e)[:200]))
            continue
        finally:
            time.sleep(REQUEST_DELAY)

        # صفحه‌های تکراری (مثلاً / و /index.html یا نسخه‌ی چاپی) فقط یک بار ذخیره می‌شوند
        digest = hashlib.sha256(clean(" ".join(t for _, t in page.segments)).encode()).hexdigest()
        if digest in seen_content:
            continue
        seen_content.add(digest)

        result.pages.append(page.url)
        result.title = result.title or page.title
        label = f"{page.title} ({page.url})" if page.title and page.title != page.url else page.url
        for loc, text in page.segments:
            result.segments.append((f"{label} · {loc}" if loc else label, text))

        for link in page.links:
            link = normalize(link)
            if link not in seen and in_scope(link, start_url):
                seen.add(link)
                queue.append(link)

    if not result.pages:
        detail = result.failures[0][1] if result.failures else "هیچ صفحه‌ای قابل خواندن نبود."
        raise loaders.UnsupportedSource(detail)
    return result
