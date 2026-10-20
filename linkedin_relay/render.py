"""Render generated HTML graphics to PNG with headless Chromium."""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def render_html(html: str, width: int, height: int, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        # CHROMIUM_PATH: use an existing Chromium instead of the Playwright download.
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        try:
            # device_scale_factor 2 gives crisp text on high-DPI screens (2160 px wide PNG).
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
            # Generated HTML must not load anything from the network.
            page.route("**/*", lambda route: route.abort()
                       if route.request.url.startswith(("http://", "https://")) else route.continue_())
            page.set_content(html, wait_until="load")
            page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": width, "height": height})
        finally:
            browser.close()
    return out_path
