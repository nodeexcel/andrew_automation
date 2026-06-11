"""Browser session management with proxy and device emulation."""

from __future__ import annotations

import logging
import random
from contextlib import contextmanager
from typing import Generator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from bot.devices import DeviceProfile, random_device

logger = logging.getLogger("trustpilot_bot")


def _parse_proxy(proxy_url: str) -> dict:
    """Convert proxy URL string to Playwright proxy config."""
    return {"server": proxy_url}


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
    logger.debug(
        "Starting browser | device=%s | proxy=%s",
        profile.name,
        proxy[:20] + "..." if proxy and len(proxy) > 20 else proxy,
    )

    with sync_playwright() as p:
        launch_kwargs: dict = {"headless": headless}
        if proxy:
            launch_kwargs["proxy"] = _parse_proxy(proxy)

        browser = p.chromium.launch(**launch_kwargs)

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
