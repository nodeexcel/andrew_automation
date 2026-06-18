"""Browser session management with proxy and device emulation."""

from __future__ import annotations

import json
import logging
import random
from contextlib import contextmanager
from typing import Generator
from urllib.parse import unquote, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from bot.devices import DeviceProfile, random_device

logger = logging.getLogger("trustpilot_bot")


def _parse_proxy(proxy_url: str) -> dict:
    """Convert proxy URL to Playwright proxy config (server + username + password)."""
    parsed = urlparse(proxy_url.strip())
    if not parsed.hostname:
        return {"server": proxy_url}

    port = parsed.port or (8080 if parsed.scheme == "http" else 1080)
    config: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}:{port}"}

    if parsed.username:
        config["username"] = unquote(parsed.username)
    if parsed.password:
        config["password"] = unquote(parsed.password)

    return config


def _proxy_log_label(proxy_url: str) -> str:
    parsed = urlparse(proxy_url.strip())
    if parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8080}"
    return proxy_url[:40]


def verify_proxy_ip(page: Page) -> str:
    """Fetch outbound IP seen by the browser (for proxy verification)."""
    try:
        page.goto("https://api.ipify.org?format=json", wait_until="domcontentloaded", timeout=30000)
        data = page.evaluate("() => document.body.innerText")
        return json.loads(data).get("ip", "unknown")
    except Exception as exc:
        logger.warning("Could not verify proxy IP: %s", exc)
        return "unknown"


@contextmanager
def browser_session(
    headless: bool = True,
    proxy: str | None = None,
    device: DeviceProfile | None = None,
) -> Generator[tuple[Playwright, Browser, BrowserContext, Page], None, None]:
    """
    Create a Playwright browser session with device emulation and optional proxy.

    Yields (playwright, browser, context, page).
    """
    profile = device or random_device()
    if proxy:
        logger.info("Using proxy: %s", _proxy_log_label(proxy))
    else:
        logger.warning("No proxy configured — browser will use your real IP")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        context_kwargs = {
            "user_agent": profile.user_agent,
            "viewport": {
                "width": profile.viewport_width,
                "height": profile.viewport_height,
            },
            "is_mobile": profile.is_mobile,
            "locale": "de-DE",
            "timezone_id": random.choice(
                ["Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/Amsterdam"]
            ),
            "extra_http_headers": {
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        }

        if proxy:
            context_kwargs["proxy"] = _parse_proxy(proxy)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            yield p, browser, context, page
        finally:
            context.close()
            browser.close()


def human_scroll(page: Page, duration_seconds: float) -> None:
    """Simulate natural scrolling over the given duration."""
    elapsed = 0.0
    scroll_position = 0

    while elapsed < duration_seconds:
        chunk = random.uniform(0.8, 2.5)
        scroll_amount = random.randint(80, 350)
        direction = 1 if random.random() > 0.15 else -1

        scroll_position = max(0, scroll_position + scroll_amount * direction)
        page.evaluate(f"window.scrollTo({{top: {scroll_position}, behavior: 'smooth'}})")

        if random.random() < 0.1:
            pause = random.uniform(1.5, 4.0)
            page.wait_for_timeout(int(pause * 1000))
            elapsed += pause
        else:
            page.wait_for_timeout(int(chunk * 1000))
            elapsed += chunk


def dwell_on_page(page: Page, min_seconds: int, max_seconds: int) -> float:
    """Stay on page for a random duration with scrolling."""
    duration = random.uniform(min_seconds, max_seconds)
    logger.debug("Dwelling on page for %.1fs", duration)

    scroll_time = duration * random.uniform(0.5, 0.8)
    human_scroll(page, scroll_time)

    remaining = duration - scroll_time
    if remaining > 0:
        page.wait_for_timeout(int(remaining * 1000))

    return duration
