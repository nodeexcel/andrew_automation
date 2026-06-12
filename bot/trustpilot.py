"""Trustpilot-specific page interactions."""

from __future__ import annotations

import logging
import random
import re
import time
import urllib.parse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from bot.browser import dwell_on_page

logger = logging.getLogger("trustpilot_bot")

TRUSTPILOT_SEARCH_SELECTORS = [
    'input[data-header-search-field="true"]',
    'input[name="query"]',
    'input[placeholder*="Unternehmen"]',
    'input[placeholder*="Suchen"]',
    'input[placeholder*="Search"]',
    '[data-testid="search-input"] input',
]

SEARCH_RESULT_SELECTORS = [
    'a[name="search-suggestion"]',
    '[data-testid="search-suggestion"] a',
    '[data-testid="search-results"] a',
    '.styles_searchResult a',
    'a[href*="/review/"]',
]

SUGGESTED_SECTION_SELECTORS = [
    '[data-testid="recommended-businesses"]',
    '[data-testid="suggested-businesses"]',
    'section:has-text("Empfohlene")',
    'section:has-text("Suggested")',
    'section:has-text("Ähnliche")',
    'section:has-text("Similar")',
    'aside:has-text("Empfohlene")',
    'aside:has-text("Suggested")',
]


def _domain_from_url(url: str) -> str:
    """Extract domain slug from a Trustpilot review URL."""
    match = re.search(r"/review/([^/?#]+)", url)
    return match.group(1).lower() if match else ""


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _matches_target(link_text: str, href: str, target_url: str, keywords: list[str]) -> bool:
    target_domain = _domain_from_url(target_url)
    href_lower = href.lower()
    text_lower = link_text.lower()

    if target_domain and target_domain in href_lower:
        return True

    for kw in keywords:
        kw_norm = _normalize(kw)
        if kw_norm and (kw_norm in _normalize(text_lower) or kw_norm in _normalize(href_lower)):
            return True

    return False


def visit_url(
    page: Page,
    url: str,
    min_duration: int,
    max_duration: int,
    wait_until: str = "domcontentloaded",
) -> bool:
    """Navigate to a URL and emulate a natural page view."""
    try:
        logger.info("Visiting: %s", url)
        page.goto(url, wait_until=wait_until, timeout=60000)
        page.wait_for_timeout(random_delay_ms(1500, 3000))
        _accept_cookies(page)
        dwell_on_page(page, min_duration, max_duration)
        return True
    except PlaywrightTimeout:
        logger.warning("Timeout visiting %s", url)
        return False
    except Exception as exc:
        logger.error("Error visiting %s: %s", url, exc)
        return False


def random_delay_ms(min_ms: int, max_ms: int) -> int:
    return random.randint(min_ms, max_ms)


def _accept_cookies(page: Page) -> None:
    """Dismiss cookie consent banner if present."""
    accepted = page.evaluate(
        """() => {
            const selectors = [
                '#onetrust-accept-btn-handler',
                'button#onetrust-accept-btn-handler',
            ];
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn) { btn.click(); return true; }
            }
            const buttons = [...document.querySelectorAll('button')];
            const match = buttons.find(b =>
                /alle akzeptieren|accept all/i.test(b.innerText)
            );
            if (match) { match.click(); return true; }
            return false;
        }"""
    )
    if accepted:
        page.wait_for_timeout(random_delay_ms(1500, 2500))


def _open_mobile_search(page: Page) -> None:
    """On mobile layouts the search field may be hidden until the icon is tapped."""
    page.evaluate(
        """() => {
            const selectors = [
                'button[aria-label="Suchen"]',
                'button[aria-label="Search"]',
            ];
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) { btn.click(); return; }
            }
        }"""
    )
    page.wait_for_timeout(random_delay_ms(500, 1200))


def _search_input_exists(page: Page) -> bool:
    _open_mobile_search(page)
    return bool(
        page.evaluate(
            """(selectors) => selectors.some((sel) => !!document.querySelector(sel))""",
            TRUSTPILOT_SEARCH_SELECTORS,
        )
    )


def _focus_and_type(page: Page, text: str) -> bool:
    """
    Focus the Trustpilot search field and type the search term.

    Uses JS focus first (Trustpilot's search input is often not Playwright-clickable),
    then types character-by-character for a natural feel.
    """
    for selector in TRUSTPILOT_SEARCH_SELECTORS:
        focused = page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }""",
            selector,
        )
        if not focused:
            continue

        for char in text:
            page.keyboard.type(char, delay=random.randint(50, 180))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.1, 0.4))

        page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            selector,
        )
        return True

    return False


def search_from_current_page(
    page: Page,
    search_term: str,
    target_url: str,
    target_keywords: list[str],
    min_duration: int,
    max_duration: int,
) -> bool:
    """Search Trustpilot from whatever page is currently open."""
    if not _search_input_exists(page):
        return False
    if not _focus_and_type(page, search_term):
        return False
    page.wait_for_timeout(random_delay_ms(1500, 3000))

    clicked = _click_search_result(page, target_url, target_keywords)
    if not clicked:
        page.keyboard.press("Enter")
        page.wait_for_timeout(random_delay_ms(2000, 4000))
        clicked = _click_search_result(page, target_url, target_keywords)
    if not clicked:
        return False

    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(random_delay_ms(1500, 3000))
    dwell_on_page(page, min_duration, max_duration)
    return True


def search_and_navigate(
    page: Page,
    source_url: str,
    search_term: str,
    target_url: str,
    target_keywords: list[str],
    min_duration: int,
    max_duration: int,
) -> bool:
    """
    Visit source page, use Trustpilot search to find target, click result, view target page.
    """
    try:
        logger.info("Search job: %s → search '%s' → %s", source_url, search_term, target_url)
        page.goto(source_url, wait_until="load", timeout=60000)
        page.wait_for_timeout(random_delay_ms(2000, 4000))
        _accept_cookies(page)

        dwell_on_page(page, min_duration // 3, max_duration // 3)

        if not _search_input_exists(page):
            logger.warning("Search input not found on %s", source_url)
            return False

        if not _focus_and_type(page, search_term):
            logger.warning("Could not type into search on %s", source_url)
            return False
        page.wait_for_timeout(random_delay_ms(1500, 3000))

        clicked = _click_search_result(page, target_url, target_keywords)
        if not clicked:
            page.keyboard.press("Enter")
            page.wait_for_timeout(random_delay_ms(2000, 4000))
            clicked = _click_search_result(page, target_url, target_keywords)

        if not clicked:
            logger.warning("Could not find search result for '%s'", search_term)
            return False

        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(random_delay_ms(1500, 3000))
        dwell_on_page(page, min_duration, max_duration)
        logger.info("Search navigation successful → %s", page.url)
        return True

    except Exception as exc:
        logger.error("Search navigation failed: %s", exc)
        return False


def _click_search_result(page: Page, target_url: str, target_keywords: list[str]) -> bool:
    for selector in SEARCH_RESULT_SELECTORS:
        links = page.locator(selector)
        count = links.count()
        for i in range(min(count, 20)):
            link = links.nth(i)
            try:
                if not link.is_visible():
                    continue
                href = link.get_attribute("href") or ""
                text = link.inner_text(timeout=2000)
                if _matches_target(text, href, target_url, target_keywords):
                    link.click()
                    return True
            except Exception:
                continue

    all_review_links = page.locator('a[href*="/review/"]')
    for i in range(min(all_review_links.count(), 30)):
        link = all_review_links.nth(i)
        try:
            if not link.is_visible():
                continue
            href = link.get_attribute("href") or ""
            text = link.inner_text(timeout=2000)
            if _matches_target(text, href, target_url, target_keywords):
                link.click()
                return True
        except Exception:
            continue

    return False


def click_suggested_website(
    page: Page,
    source_url: str,
    target_url: str,
    target_keywords: list[str],
    min_duration: int,
    max_duration: int,
) -> bool:
    """
    Visit source page and click the target if it appears in suggested/recommended section.
    """
    try:
        logger.info("Suggested click job: %s → looking for %s", source_url, target_url)
        page.goto(source_url, wait_until="load", timeout=60000)
        page.wait_for_timeout(random_delay_ms(2000, 4000))
        _accept_cookies(page)

        dwell_on_page(page, min_duration // 4, max_duration // 4)

        clicked = _click_in_suggested_section(page, target_url, target_keywords)
        if not clicked:
            clicked = _click_any_matching_link(page, target_url, target_keywords)

        if not clicked:
            logger.info("Target not found in suggested section on %s", source_url)
            return False

        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(random_delay_ms(1500, 3000))
        dwell_on_page(page, min_duration, max_duration)
        logger.info("Suggested click successful → %s", page.url)
        return True

    except Exception as exc:
        logger.error("Suggested click failed: %s", exc)
        return False


def _click_in_suggested_section(
    page: Page, target_url: str, target_keywords: list[str]
) -> bool:
    for section_selector in SUGGESTED_SECTION_SELECTORS:
        section = page.locator(section_selector).first
        if section.count() == 0 or not section.is_visible():
            continue

        links = section.locator('a[href*="/review/"]')
        for i in range(links.count()):
            link = links.nth(i)
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text(timeout=2000)
                if _matches_target(text, href, target_url, target_keywords):
                    link.scroll_into_view_if_needed()
                    page.wait_for_timeout(random_delay_ms(500, 1500))
                    link.click()
                    return True
            except Exception:
                continue

    return False


def _click_any_matching_link(
    page: Page, target_url: str, target_keywords: list[str]
) -> bool:
    """Fallback: find any visible link matching target on the page."""
    links = page.locator('a[href*="/review/"]')
    for i in range(min(links.count(), 50)):
        link = links.nth(i)
        try:
            if not link.is_visible():
                continue
            href = link.get_attribute("href") or ""
            text = link.inner_text(timeout=2000)
            if _matches_target(text, href, target_url, target_keywords):
                link.scroll_into_view_if_needed()
                page.wait_for_timeout(random_delay_ms(500, 1500))
                link.click()
                return True
        except Exception:
            continue
    return False


def build_search_url(locale: str, keyword: str) -> str:
    """Build a Trustpilot search results URL."""
    encoded = urllib.parse.quote(keyword)
    base = f"https://{locale}.trustpilot.com" if locale != "www" else "https://www.trustpilot.com"
    return f"{base}/search?query={encoded}"
