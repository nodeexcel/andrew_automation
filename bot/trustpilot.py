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


def _url_matches_slug(page_url: str, slug: str) -> bool:
    if not slug:
        return False
    normalized = slug.lower().replace("www.", "")
    return normalized in page_url.lower()


def _is_review_page(page_url: str) -> bool:
    return "/review/" in page_url and "trustpilot.com" in page_url


def _wait_page_stable(page: Page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(random_delay_ms(500, 1200))


def _safe_evaluate(page: Page, script: str, arg=None, retries: int = 3):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            _wait_page_stable(page)
            if arg is None:
                return page.evaluate(script)
            return page.evaluate(script, arg)
        except Exception as exc:
            last_exc = exc
            logger.debug("Evaluate attempt %d failed: %s", attempt + 1, exc)
            page.wait_for_timeout(random_delay_ms(800, 1500))
    if last_exc:
        raise last_exc
    return None


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
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    try:
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
    except Exception:
        return
    if accepted:
        page.wait_for_timeout(random_delay_ms(1500, 2500))


def _open_mobile_search(page: Page) -> None:
    """On mobile layouts the search field may be hidden until the icon is tapped."""
    try:
        _safe_evaluate(
            page,
            """() => {
                const selectors = [
                    'button[aria-label="Suchen"]',
                    'button[aria-label="Search"]',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) { btn.click(); return; }
                }
            }""",
            retries=2,
        )
    except Exception:
        pass
    page.wait_for_timeout(random_delay_ms(500, 1200))


def _search_input_exists(page: Page) -> bool:
    _open_mobile_search(page)
    try:
        return bool(
            _safe_evaluate(
                page,
                """(selectors) => selectors.some((sel) => !!document.querySelector(sel))""",
                TRUSTPILOT_SEARCH_SELECTORS,
                retries=2,
            )
        )
    except Exception:
        return False


def _focus_and_type(page: Page, text: str) -> bool:
    """
    Focus the Trustpilot search field and type the search term.

    Uses JS focus first (Trustpilot's search input is often not Playwright-clickable),
    then types character-by-character for a natural feel.
    """
    for selector in TRUSTPILOT_SEARCH_SELECTORS:
        try:
            focused = _safe_evaluate(
                page,
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    el.focus();
                    el.value = '';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    return true;
                }""",
                selector,
                retries=2,
            )
        except Exception:
            continue
        if not focused:
            continue

        for char in text:
            page.keyboard.type(char, delay=random.randint(50, 180))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.1, 0.4))

        try:
            _safe_evaluate(
                page,
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (el) el.dispatchEvent(new Event('input', { bubbles: true }));
                }""",
                selector,
                retries=2,
            )
        except Exception:
            pass
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


def _click_search_result(
    page: Page,
    target_url: str,
    target_keywords: list[str],
    avoid_slugs: set[str] | None = None,
    pick_first_valid: bool = False,
) -> bool:
    avoid = list(avoid_slugs or set())
    target_slug = _domain_from_url(target_url)

    # Prefer Playwright locator click — more stable than evaluate during navigation
    if target_slug and not pick_first_valid:
        for slug_variant in {target_slug, target_slug.replace("www.", "")}:
            try:
                link = page.locator(f'a[href*="/review/{slug_variant}"]').first
                if link.count() > 0 and link.is_visible():
                    link.click(timeout=5000)
                    _wait_page_stable(page)
                    return True
            except Exception:
                pass

    for attempt in range(3):
        try:
            _wait_page_stable(page)
            clicked = _safe_evaluate(
                page,
                """({ pickFirst, avoid, targetSlug, keywords }) => {
                    const norm = (t) => (t || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                    const kws = keywords.map(norm);
                    const avoidNorm = avoid.map(norm).filter(Boolean);
                    const links = [...document.querySelectorAll('a[href*="/review/"]')]
                        .filter(el => el.offsetParent !== null && el.href.startsWith('http'));

                    for (const el of links) {
                        const href = el.href.toLowerCase();
                        const text = (el.innerText || '').toLowerCase();
                        const blob = norm(href + text);
                        if (avoidNorm.some(s => s && blob.includes(s))) continue;

                        if (pickFirst) {
                            el.click();
                            return true;
                        }
                        if (targetSlug && href.includes(targetSlug.toLowerCase())) {
                            el.click();
                            return true;
                        }
                        if (kws.some(k => k && (blob.includes(k) || norm(el.innerText).includes(k)))) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                {
                    "pickFirst": pick_first_valid,
                    "avoid": avoid,
                    "targetSlug": target_slug,
                    "keywords": target_keywords,
                },
                retries=2,
            )
            if clicked:
                _wait_page_stable(page)
                return True
        except Exception as exc:
            logger.debug("Search click attempt %d failed: %s", attempt + 1, exc)
            page.wait_for_timeout(random_delay_ms(1000, 2000))

    return False


def search_and_open(
    page: Page,
    search_term: str,
    match_url: str,
    match_keywords: list[str],
    min_duration: int,
    max_duration: int,
    avoid_slugs: set[str] | None = None,
    pick_first_valid: bool = False,
) -> bool:
    """
    Type into Trustpilot search and click a result — never uses the address bar for review URLs.
    """
    expected_slug = _domain_from_url(match_url) or search_term.lower().replace("www.", "")

    for search_attempt in range(2):
        try:
            if not _search_input_exists(page):
                logger.warning("Search input not found on %s", page.url)
                return False
            if not _focus_and_type(page, search_term):
                logger.warning("Could not type search term '%s'", search_term)
                return False
            page.wait_for_timeout(random_delay_ms(1500, 3000))

            clicked = _click_search_result(
                page, match_url, match_keywords, avoid_slugs, pick_first_valid
            )
            if not clicked:
                page.keyboard.press("Enter")
                page.wait_for_timeout(random_delay_ms(2000, 4000))
                clicked = _click_search_result(
                    page, match_url, match_keywords, avoid_slugs, pick_first_valid
                )
            if not clicked:
                return False

            _wait_page_stable(page)

            if pick_first_valid:
                if not _is_review_page(page.url):
                    logger.warning("Browse search did not land on a review page: %s", page.url)
                    return False
            elif expected_slug and not _url_matches_slug(page.url, expected_slug):
                logger.warning(
                    "Search landed on wrong page: %s (wanted %s) — retry %d/2",
                    page.url,
                    expected_slug,
                    search_attempt + 1,
                )
                page.wait_for_timeout(random_delay_ms(1000, 2000))
                continue

            dwell_on_page(page, max(5, min_duration // 3), max(12, max_duration // 3))
            return True
        except Exception as exc:
            logger.warning("Search and open failed for '%s': %s", search_term, exc)
            page.wait_for_timeout(random_delay_ms(1000, 2000))

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
