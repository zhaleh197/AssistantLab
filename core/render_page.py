"""رندر صفحه‌ی وب با مرورگر headless، در پروسه‌ای جدا از Streamlit.

استفاده: python -m core.render_page <url>   →   HTML نهایی (UTF-8) در stdout
"""
import sys
from urllib.parse import urlparse

import config
from core.loaders import is_public_host

SKIPPED_RESOURCES = {"image", "media", "font"}


def render(url: str) -> str:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()

            def guard(route):
                req = route.request
                parsed = urlparse(req.url)
                if req.resource_type in SKIPPED_RESOURCES:
                    return route.abort()
                if parsed.scheme in ("data", "blob"):
                    return route.continue_()
                # درخواست‌های خود صفحه (اسکریپت، fetch، ...) هم نباید به شبکه‌ی داخلی برسند
                if parsed.scheme in ("http", "https") and is_public_host(parsed.hostname):
                    return route.continue_()
                return route.abort()

            page.route("**/*", guard)
            page.goto(url, wait_until="load", timeout=config.RENDER_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeout:
                pass  # بعضی سایت‌ها هیچ‌وقت کاملاً ساکت نمی‌شوند؛ همان محتوای فعلی کافی است
            return page.content()
        finally:
            browser.close()


if __name__ == "__main__":
    sys.stdout.buffer.write(render(sys.argv[1]).encode("utf-8"))
