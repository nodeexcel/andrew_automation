"""Deep multi-page Trustpilot journeys with external click-out."""

from __future__ import annotations

import logging
import random
import re
from urllib.parse import urlparse

from playwright.sync_api import Page

from bot.browser import dwell_on_page
from bot import trustpilot

logger = logging.getLogger("trustpilot_bot")

TRUSTPILOT_LINK_SELECTORS = [
    'a[name="search-suggestion"]',
    'a[href*="/review/"]',
    'a[href*="/categories/"]',
    'a[href*="/users/"]',
]

EXTERNAL_LINK_SELECTORS = [
    'a[data-business-unit-link="true"]',
    'a[rel*="nofollow"][target="_blank"]',
    'a[href^="http"]:not([href*="trustpilot.com"])',
]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"{parsed.netloc}{path}".lower()


def _external_domains(external_urls: list[str], trustpilot_target: str, keywords: list[str]) -> set[str]:
    domains: set[str] = set()
    for url in external_urls:
        host = urlparse(url).netloc.lower().replace("www.", "")
        if host:
            domains.add(host)
    tp_slug = trustpilot._domain_from_url(trustpilot_target)
    if tp_slug:
        domains.add(tp_slug.lower())
    for kw in keywords:
        cleaned = re.sub(r"[^a-z0-9.]", "", kw.lower())
        if "." in cleaned:
            domains.add(cleaned.replace("www.", ""))
    return domains


def _collect_internal_links(page: Page) -> list[dict[str, str]]:
    return page.evaluate(
        """() => {
            const out = [];
            const seen = new Set();
            const selectors = [
                'a[name="search-suggestion"]',
                'a[href*="/review/"]',
                'a[href*="/categories/"]',
            ];
            for (const sel of selectors) {
                for (const el of document.querySelectorAll(sel)) {
                    if (!el.href || el.offsetParent === null) continue;
                    if (!el.href.includes('trustpilot.com')) continue;
                    const key = el.href.split('#')[0];
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({ href: key, text: (el.innerText || '').slice(0, 120) });
                }
            }
            return out;
        }"""
    )


def _pick_browse_link(
    links: list[dict[str, str]],
    visited: set[str],
    current_url: str,
    avoid_domains: set[str],
) -> dict[str, str] | None:
    current_norm = _normalize_url(current_url)
    candidates = []
    for link in links:
        norm = _normalize_url(link["href"])
        if norm == current_norm or norm in visited:
            continue
        if any(d in link["href"].lower() for d in avoid_domains):
            continue
        candidates.append(link)
    if not candidates:
        return None
    return random.choice(candidates)


def _short_dwell(page: Page, min_sec: int, max_sec: int) -> None:
    dwell_on_page(page, max(5, min_sec // 4), max(12, max_sec // 4))


def _browse_trustpilot_depth(
    page: Page,
    start_url: str,
    depth: int,
    avoid_domains: set[str],
    min_duration: int,
    max_duration: int,
) -> int:
    """Click through `depth` Trustpilot pages. Returns pages visited."""
    page.goto(start_url, wait_until="load", timeout=60000)
    page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
    trustpilot._accept_cookies(page)
    _short_dwell(page, min_duration, max_duration)

    visited: set[str] = {_normalize_url(start_url)}
    pages_done = 1

    for step in range(depth):
        links = _collect_internal_links(page)
        pick = _pick_browse_link(links, visited, page.url, avoid_domains)
        if not pick:
            logger.debug("No browse link at step %d on %s", step + 1, page.url)
            break

        logger.info("Journey step %d/%d → %s", step + 1, depth, pick["href"])
        try:
            page.goto(pick["href"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3500))
            visited.add(_normalize_url(page.url))
            pages_done += 1
            _short_dwell(page, min_duration, max_duration)
        except Exception as exc:
            logger.debug("Browse step failed: %s", exc)
            break

    return pages_done


def _steer_to_target(
    page: Page,
    source_url: str,
    trustpilot_target: str,
    keywords: list[str],
    search_term: str,
    min_duration: int,
    max_duration: int,
    use_search: bool,
) -> bool:
    """Navigate from current page to the target Trustpilot review page."""
    if trustpilot._matches_target("", page.url, trustpilot_target, keywords):
        return True

    if trustpilot._click_any_matching_link(page, trustpilot_target, keywords):
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3000))
        _short_dwell(page, min_duration, max_duration)
        return True

    if trustpilot._click_in_suggested_section(page, trustpilot_target, keywords):
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3000))
        _short_dwell(page, min_duration, max_duration)
        return True

    if use_search and search_term:
        return trustpilot.search_from_current_page(
            page,
            search_term,
            trustpilot_target,
            keywords,
            min_duration,
            max_duration,
        )

    return False


def click_out_to_external(
    page: Page,
    external_urls: list[str],
    trustpilot_target: str,
    keywords: list[str],
    min_duration: int,
    max_duration: int,
) -> bool:
    """Click from Trustpilot review page to the real business website."""
    domains = _external_domains(external_urls, trustpilot_target, keywords)
    logger.info("Looking for external click-out → %s", ", ".join(domains))

    for domain in domains:
        locator = page.locator(f'a[href*="{domain}"]:not([href*="trustpilot.com"])')
        count = locator.count()
        for i in range(count):
            link = locator.nth(i)
            try:
                if not link.is_visible():
                    continue
                href = link.get_attribute("href") or ""
                if "trustpilot.com" in href:
                    continue
                link.scroll_into_view_if_needed()
                page.wait_for_timeout(trustpilot.random_delay_ms(500, 1200))
                link.click()
                page.wait_for_load_state("domcontentloaded", timeout=45000)
                page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
                dwell_on_page(page, min_duration, max_duration)
                logger.info("Clicked out to external site → %s", page.url)
                return True
            except Exception:
                continue

    for selector in EXTERNAL_LINK_SELECTORS:
        links = page.locator(selector)
        for i in range(min(links.count(), 10)):
            link = links.nth(i)
            try:
                if not link.is_visible():
                    continue
                href = (link.get_attribute("href") or "").lower()
                if not href.startswith("http") or "trustpilot.com" in href:
                    continue
                if domains and not any(d in href for d in domains):
                    continue
                link.scroll_into_view_if_needed()
                page.wait_for_timeout(trustpilot.random_delay_ms(500, 1200))
                link.click()
                page.wait_for_load_state("domcontentloaded", timeout=45000)
                page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
                dwell_on_page(page, min_duration, max_duration)
                logger.info("Clicked out via selector → %s", page.url)
                return True
            except Exception:
                continue

    if external_urls:
        fallback = random.choice(external_urls)
        logger.info("No on-page external link; navigating to %s", fallback)
        return trustpilot.visit_url(page, fallback, min_duration, max_duration)

    return False


def run_deep_journey(
    page: Page,
    start_url: str,
    trustpilot_target: str,
    external_urls: list[str],
    keywords: list[str],
    search_term: str,
    min_depth: int,
    max_depth: int,
    min_duration: int,
    max_duration: int,
    click_external: bool = True,
    steer_via_search: bool = False,
) -> bool:
    """
    Natural journey: browse 10+ Trustpilot pages, reach target review, click out to real site.
    """
    depth = random.randint(min_depth, max_depth)
    avoid = _external_domains(external_urls, trustpilot_target, keywords)

    logger.info(
        "Deep journey starting | depth=%d | %s → %s",
        depth,
        start_url,
        trustpilot_target,
    )

    pages = _browse_trustpilot_depth(
        page, start_url, depth, avoid, min_duration, max_duration
    )
    logger.info("Browsed %d Trustpilot pages (target depth: %d)", pages, depth)

    if pages < min_depth:
        extra = min_depth - pages
        pages += _browse_trustpilot_depth(
            page, page.url, extra, avoid, min_duration, max_duration
        )
        logger.info("Extended browse to %d pages total", pages)

    on_target = _steer_to_target(
        page,
        start_url,
        trustpilot_target,
        keywords,
        search_term,
        min_duration,
        max_duration,
        use_search=steer_via_search,
    )
    if not on_target:
        logger.warning("Could not reach Trustpilot target after deep journey")
        return False

    dwell_on_page(page, min_duration, max_duration)
    logger.info("Reached Trustpilot target → %s", page.url)

    if click_external and external_urls:
        return click_out_to_external(
            page, external_urls, trustpilot_target, keywords, min_duration, max_duration
        )

    return True
