"""Search-only Trustpilot journeys using List A, List B, and target lists."""

from __future__ import annotations

import logging
import random
import re
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

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
        page.goto(home, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
        try:
            trustpilot._accept_cookies(page)
        except Exception:
            pass
        _short_dwell(page, 8, 15)
        return True
    except Exception as exc:
        logger.error("Could not open Trustpilot home: %s", exc)
        return False


def _ensure_searchable(page: Page, locale: str) -> bool:
    """Make sure Trustpilot search is available — go home if stuck on a bad page."""
    home_host = "www.trustpilot.com" if locale in ("www", "") else f"{locale}.trustpilot.com"
    parsed = urlparse(page.url)

    if "trustpilot.com" in parsed.netloc and parsed.netloc != home_host:
        logger.info("Regional redirect detected (%s) — returning to %s", parsed.netloc, home_host)
        return _open_trustpilot_home(page, locale)

    if trustpilot._search_input_exists(page):
        return True

    logger.info("Search input missing on %s — returning to Trustpilot home", page.url)
    return _open_trustpilot_home(page, locale)


def _browse_via_search(
    page: Page,
    locale: str,
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
            match_keywords=[term, term.replace("www.", "")],
            avoid_slugs=avoid_slugs,
            pick_first_valid=False,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        if ok and trustpilot._url_matches_slug(page.url, term):
            pages += 1
            logger.info("Landed via search → %s", page.url)
        else:
            logger.warning("Browse search failed for '%s' — retrying", term)
            _ensure_searchable(page, locale)
            page.wait_for_timeout(trustpilot.random_delay_ms(1000, 2000))

    return pages


def _land_rank_page_via_search(
    page: Page,
    rank_terms: list[str],
    locale: str,
    min_duration: int,
    max_duration: int,
    max_attempts: int = 5,
) -> tuple[bool, str]:
    """Pick a List B page at random and reach it via Trustpilot search."""
    tried: set[str] = set()
    last_term = ""

    logger.info("Starting List B — fresh Trustpilot home before rank page search")
    if not _open_trustpilot_home(page, locale):
        return False, ""

    for attempt in range(max_attempts):
        pool = [t for t in rank_terms if t.lower() not in tried] or rank_terms
        term = random.choice(pool)
        tried.add(term.lower())
        last_term = term
        match_url = f"https://www.trustpilot.com/review/{term}"
        logger.info("Rank page — search '%s' (List B, attempt %d/%d)", term, attempt + 1, max_attempts)

        if not _ensure_searchable(page, locale):
            continue

        ok = trustpilot.search_and_open(
            page,
            search_term=term,
            match_url=match_url,
            match_keywords=[term, term.replace("www.", "")],
            min_duration=min_duration,
            max_duration=max_duration,
        )
        if ok and trustpilot._url_matches_slug(page.url, term):
            return True, term
        if ok:
            logger.warning("Rank search landed on wrong page: %s (wanted %s)", page.url, term)
        _open_trustpilot_home(page, locale)

    return False, last_term


def _reach_target_from_rank_page(
    page: Page,
    locale: str,
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

    search_terms: list[str] = []
    for candidate in [search_term, *target_keywords]:
        if candidate and candidate.lower() not in {s.lower() for s in search_terms}:
            search_terms.append(candidate)
    if not search_terms:
        search_terms = [trustpilot._domain_from_url(trustpilot_target)]

    for i, try_term in enumerate(search_terms):
        logger.info("Target — search '%s' from rank page (attempt %d/%d)", try_term, i + 1, len(search_terms))
        _ensure_searchable(page, locale)
        if trustpilot.search_and_open(
            page,
            search_term=try_term,
            match_url=trustpilot_target,
            match_keywords=target_keywords,
            min_duration=min_duration,
            max_duration=max_duration,
        ):
            if trustpilot._matches_target("", page.url, trustpilot_target, target_keywords):
                logger.info("Target reached via search → %s", page.url)
                return True

    return False


def _normalize_host(host: str) -> str:
    return host.lower().replace("www.", "").strip()


def _is_external_url(url: str) -> bool:
    try:
        return bool(url) and "trustpilot.com" not in urlparse(url).netloc.lower()
    except Exception:
        return False


def _external_hosts(
    external_urls: list[str],
    trustpilot_target: str,
    target_keywords: list[str],
) -> set[str]:
    """Domains we may click out to (from config + target slug/keywords)."""
    hosts: set[str] = set()
    for raw in external_urls:
        if not raw or "trustpilot.com" in raw:
            continue
        url = raw if "://" in raw else f"https://{raw}"
        host = urlparse(url).netloc
        if host:
            hosts.add(_normalize_host(host))

    match = re.search(r"/review/([^/?#]+)", trustpilot_target or "")
    if match:
        hosts.add(_normalize_host(match.group(1)))

    for kw in target_keywords:
        k = kw.strip()
        if k and ("." in k or (match and " " not in k)):
            hosts.add(_normalize_host(k))

    return {h for h in hosts if h and "trustpilot" not in h}


def _host_matches_allowed(host: str, allowed: set[str]) -> bool:
    if not host or "trustpilot.com" in host:
        return False
    if not allowed:
        return True
    h = _normalize_host(host)
    return h in allowed or any(h == d or h.endswith(f".{d}") for d in allowed)


def _click_link_to_external(
    page: Page,
    locator,
    min_duration: int,
    max_duration: int,
) -> str | None:
    """Click a link; return external URL (handles new tab or same-tab navigation)."""
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(trustpilot.random_delay_ms(500, 1200))
    context = page.context

    try:
        with context.expect_page(timeout=10000) as new_page_info:
            locator.click(timeout=10000)
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded", timeout=45000)
        new_page.wait_for_timeout(trustpilot.random_delay_ms(2000, 4000))
        if _is_external_url(new_page.url):
            dwell_on_page(new_page, min_duration, max_duration)
            logger.info("Clicked out (new tab) → %s", new_page.url)
            return new_page.url
        new_page.close()
    except PlaywrightTimeoutError:
        pass
    except Exception as exc:
        logger.debug("New-tab click-out: %s", exc)

    page.wait_for_timeout(trustpilot.random_delay_ms(1500, 3000))
    if _is_external_url(page.url):
        dwell_on_page(page, min_duration, max_duration)
        logger.info("Clicked out (same tab) → %s", page.url)
        return page.url

    return None


_BUSINESS_LINK_SELECTORS = (
    'a[data-business-unit-link="true"]',
    'a[data-business-unit-website-link="true"]',
    'a[name="visit-website-button"]',
    'header a[target="_blank"][href^="http"]:not([href*="trustpilot"])',
)


def click_out_to_external(
    page: Page,
    external_urls: list[str],
    trustpilot_target: str,
    target_keywords: list[str],
    min_duration: int,
    max_duration: int,
) -> str | None:
    """Click from Trustpilot review page to the real business website. Returns external URL or None."""
    allowed = _external_hosts(external_urls, trustpilot_target, target_keywords)
    if not allowed:
        logger.debug("External click-out skipped — no external domains")
        return None

    logger.info("External click-out → %s", ", ".join(sorted(allowed)))

    for selector in _BUSINESS_LINK_SELECTORS:
        link = page.locator(selector).first
        if link.count() == 0:
            continue
        try:
            href = link.get_attribute("href") or ""
            host = _normalize_host(urlparse(href).netloc)
            if href and _host_matches_allowed(host, allowed):
                out = _click_link_to_external(page, link, min_duration, max_duration)
                if out:
                    return out
        except Exception as exc:
            logger.debug("Selector %s failed: %s", selector, exc)

    for label in ("Visit website", "Open website", "Go to website"):
        try:
            link = page.get_by_role("link", name=label, exact=False).first
            if link.count() == 0:
                continue
            href = link.get_attribute("href") or ""
            host = _normalize_host(urlparse(href).netloc)
            if href and _host_matches_allowed(host, allowed):
                out = _click_link_to_external(page, link, min_duration, max_duration)
                if out:
                    return out
        except Exception:
            continue

    candidates: list[str] = page.evaluate(
        """(allowed) => {
            const links = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('a[href]')) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
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
            host = _normalize_host(urlparse(href).netloc)
            if not _host_matches_allowed(host, allowed):
                continue
            link = page.locator(f'a[href="{href}"]').first
            if link.count() == 0:
                continue
            out = _click_link_to_external(page, link, min_duration, max_duration)
            if out:
                return out
        except Exception:
            continue

    return None


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
    pages = _browse_via_search(page, locale, random_terms, depth, avoid, min_duration, max_duration)
    logger.info("Random browse complete — %d pages via search", pages)
    result.final_url = page.url

    if browse_only:
        result.success = pages >= 1
        if not result.success:
            result.error = "Random browse did not complete"
        return result

    ok, rank_term = _land_rank_page_via_search(page, rank_terms, locale, min_duration, max_duration)
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
        locale,
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

    if click_external:
        out_url = click_out_to_external(
            page,
            external_urls,
            trustpilot_target,
            target_keywords,
            min_duration,
            max_duration,
        )
        if out_url:
            result.external_clicked = True
            result.final_url = out_url
        elif _external_hosts(external_urls, trustpilot_target, target_keywords):
            logger.warning("External click-out failed — target page was still reached")

    result.success = result.target_reached
    return result
