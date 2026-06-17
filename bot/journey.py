"""Search-only Trustpilot journeys using List A, List B, and target lists."""

from __future__ import annotations

import logging
import random
import re
from urllib.parse import urlparse

from playwright.sync_api import Page

from bot.browser import dwell_on_page
from bot.journey_result import JourneyResult
from bot import trustpilot

logger = logging.getLogger("trustpilot_bot")


def _short_dwell(page: Page, min_sec: int, max_sec: int) -> None:
    dwell_on_page(page, max(5, min_sec // 4), max(12, max_sec // 4))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _avoid_slugs(
    rank_terms: list[str],
    target_url: str,
    target_keywords: list[str],
) -> set[str]:
    slugs = {_slug(trustpilot._domain_from_url(target_url))}
    slugs.update(_slug(k) for k in target_keywords)
    slugs.update(_slug(t) for t in rank_terms)
    return {s for s in slugs if s}


def _open_trustpilot_home(page: Page, locale: str) -> bool:
    """Only allowed direct URL load — Trustpilot homepage."""
    home = "https://www.trustpilot.com" if locale in ("www", "") else f"https://{locale}.trustpilot.com"
    logger.info("Opening Trustpilot home (search-only mode): %s", home)
    try:
        page.goto(home, wait_until="load", timeout=60000)
        page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
        trustpilot._accept_cookies(page)
        _short_dwell(page, 8, 15)
        return True
    except Exception as exc:
        logger.error("Could not open Trustpilot home: %s", exc)
        return False


def _browse_via_search(
    page: Page,
    random_terms: list[str],
    depth: int,
    avoid_slugs: set[str],
    min_duration: int,
    max_duration: int,
) -> int:
    """Search List A terms and click results — no address-bar review URLs."""
    pages = 1
    used_terms: set[str] = set()

    for step in range(depth):
        pool = [t for t in random_terms if t.lower() not in used_terms] or random_terms
        term = random.choice(pool)
        used_terms.add(term.lower())

        logger.info("Random browse %d/%d — search '%s'", step + 1, depth, term)
        ok = trustpilot.search_and_open(
            page,
            search_term=term,
            match_url=f"https://www.trustpilot.com/review/{term}",
            match_keywords=[term],
            avoid_slugs=avoid_slugs,
            pick_first_valid=True,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        if ok:
            pages += 1
            logger.info("Landed via search → %s", page.url)
        else:
            logger.warning("Browse search failed for '%s' — retrying", term)
            page.wait_for_timeout(trustpilot.random_delay_ms(1000, 2000))

    return pages


def _land_rank_page_via_search(
    page: Page,
    rank_terms: list[str],
    min_duration: int,
    max_duration: int,
) -> tuple[bool, str]:
    """Pick a List B page at random and reach it via Trustpilot search."""
    term = random.choice(rank_terms)
    match_url = f"https://www.trustpilot.com/review/{term}"
    logger.info("Rank page — search '%s' (List B)", term)
    ok = trustpilot.search_and_open(
        page,
        search_term=term,
        match_url=match_url,
        match_keywords=[term, term.replace("www.", "")],
        min_duration=min_duration,
        max_duration=max_duration,
    )
    return ok, term


def _reach_target_from_rank_page(
    page: Page,
    trustpilot_target: str,
    target_keywords: list[str],
    search_term: str,
    prefer_suggested: bool,
    min_duration: int,
    max_duration: int,
) -> bool:
    """From a List B page, reach target via suggested click or Trustpilot search."""
    if trustpilot._matches_target("", page.url, trustpilot_target, target_keywords):
        return True

    if prefer_suggested:
        if trustpilot._click_in_suggested_section(page, trustpilot_target, target_keywords):
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3000))
            _short_dwell(page, min_duration, max_duration)
            if trustpilot._matches_target("", page.url, trustpilot_target, target_keywords):
                logger.info("Target reached via suggested click → %s", page.url)
                return True

        if trustpilot._click_any_matching_link(page, trustpilot_target, target_keywords):
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3000))
            _short_dwell(page, min_duration, max_duration)
            if trustpilot._matches_target("", page.url, trustpilot_target, target_keywords):
                logger.info("Target reached via on-page link → %s", page.url)
                return True

    term = search_term or (target_keywords[0] if target_keywords else trustpilot._domain_from_url(trustpilot_target))
    logger.info("Target — search '%s' from rank page", term)
    if trustpilot.search_and_open(
        page,
        search_term=term,
        match_url=trustpilot_target,
        match_keywords=target_keywords,
        min_duration=min_duration,
        max_duration=max_duration,
    ):
        logger.info("Target reached via search → %s", page.url)
        return True

    return False


def click_out_to_external(
    page: Page,
    external_urls: list[str],
    min_duration: int,
    max_duration: int,
) -> bool:
    """Click from Trustpilot review page to the real business website."""
    allowed = {
        urlparse(u).netloc.lower().replace("www.", "")
        for u in external_urls
        if u and "trustpilot.com" not in u
    }
    logger.info("External click-out → %s", ", ".join(allowed) or "any")

    business_link = page.locator('a[data-business-unit-link="true"]').first
    if business_link.count() > 0:
        try:
            href = business_link.get_attribute("href") or ""
            host = urlparse(href).netloc.lower().replace("www.", "")
            if host and "trustpilot.com" not in host and (
                not allowed or host in allowed or any(host.endswith(d) for d in allowed)
            ):
                business_link.scroll_into_view_if_needed()
                page.wait_for_timeout(trustpilot.random_delay_ms(500, 1200))
                business_link.click()
                page.wait_for_load_state("domcontentloaded", timeout=45000)
                page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
                if "trustpilot.com" not in urlparse(page.url).netloc:
                    dwell_on_page(page, min_duration, max_duration)
                    logger.info("Clicked out via business link → %s", page.url)
                    return True
        except Exception:
            pass

    candidates = page.evaluate(
        """(allowed) => {
            const links = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('a[href]')) {
                if (!el.href || el.offsetParent === null) continue;
                let host = '';
                try { host = new URL(el.href).hostname.replace(/^www\\./, ''); } catch { continue; }
                if (!host || host.includes('trustpilot.com')) continue;
                if (allowed.length && !allowed.some(d => host === d || host.endsWith('.' + d))) continue;
                if (seen.has(el.href)) continue;
                seen.add(el.href);
                links.push(el.href);
            }
            return links;
        }""",
        list(allowed),
    )

    for href in candidates:
        try:
            link = page.locator(f'a[href="{href}"]').first
            if link.count() == 0:
                continue
            link.click()
            page.wait_for_load_state("domcontentloaded", timeout=45000)
            page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
            if "trustpilot.com" not in urlparse(page.url).netloc:
                dwell_on_page(page, min_duration, max_duration)
                logger.info("Clicked out → %s", page.url)
                return True
        except Exception:
            continue

    return not external_urls


def run_search_journey(
    page: Page,
    locale: str,
    random_terms: list[str],
    rank_terms: list[str],
    trustpilot_target: str,
    target_keywords: list[str],
    external_urls: list[str],
    search_term: str,
    min_depth: int,
    max_depth: int,
    min_duration: int,
    max_duration: int,
    click_external: bool = True,
    prefer_suggested: bool = False,
    browse_only: bool = False,
) -> JourneyResult:
    """
    Full search-only journey:
    Home → List A random searches → List B rank page → target → optional external click.
    """
    result = JourneyResult(success=False, final_url="")

    if not random_terms:
        result.error = "List A (random browse) is empty"
        logger.error(result.error)
        return result
    if not browse_only and not rank_terms:
        result.error = "List B (rank pages) is empty"
        logger.error(result.error)
        return result

    if not _open_trustpilot_home(page, locale):
        result.error = "Could not open Trustpilot home"
        return result

    result.final_url = page.url
    depth = random.randint(min_depth, max_depth)
    avoid = _avoid_slugs(rank_terms, trustpilot_target, target_keywords)
    pages = _browse_via_search(page, random_terms, depth, avoid, min_duration, max_duration)
    logger.info("Random browse complete — %d pages via search", pages)
    result.final_url = page.url

    if browse_only:
        result.success = pages >= 1
        if not result.success:
            result.error = "Random browse did not complete"
        return result

    ok, rank_term = _land_rank_page_via_search(page, rank_terms, min_duration, max_duration)
    result.rank_page_term = rank_term
    result.rank_page_url = page.url if ok else ""
    result.final_url = page.url
    if not ok:
        result.error = "Could not reach rank page from List B via search"
        logger.warning(result.error)
        return result
    logger.info("On rank page (List B) → %s", page.url)

    if not _reach_target_from_rank_page(
        page,
        trustpilot_target,
        target_keywords,
        search_term or rank_term,
        prefer_suggested,
        min_duration,
        max_duration,
    ):
        result.error = "Could not reach target from rank page"
        logger.warning(result.error)
        return result

    result.target_reached = trustpilot._matches_target("", page.url, trustpilot_target, target_keywords)
    result.final_url = page.url
    dwell_on_page(page, min_duration, max_duration)
    logger.info("On target page → %s", page.url)

    if click_external and external_urls:
        if click_out_to_external(page, external_urls, min_duration, max_duration):
            result.external_clicked = True
            result.final_url = page.url
        else:
            logger.warning("External click-out failed — target page was still reached")

    result.success = result.target_reached
    return result
