"""Job definitions and execution."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from enum import Enum

from bot.browser import browser_session
from bot.config import Campaign, Settings
from bot.devices import DESKTOP_PROFILES, random_device
from bot import journey
from bot.reporting import JobResult

logger = logging.getLogger("trustpilot_bot")


class JobType(str, Enum):
    DIRECT_VISIT = "direct_visit"
    SEARCH_NAVIGATE = "search_navigate"
    SUGGESTED_CLICK = "suggested_click"
    TARGET_DIRECT = "target_direct"


@dataclass
class Job:
    job_type: JobType
    campaign_name: str
    random_browse_terms: list[str]
    rank_page_terms: list[str]
    target_url: str
    search_term: str
    target_keywords: list[str]
    external_target_urls: list[str]
    scheduled_at: float


def build_job_queue(campaigns: list[Campaign], run_duration_hours: float) -> list[Job]:
    jobs: list[Job] = []
    run_seconds = run_duration_hours * 3600
    start_time = time.time()

    for campaign in campaigns:
        if not campaign.enabled:
            continue

        if not campaign.random_browse_terms:
            logger.warning("Campaign '%s' has empty List A", campaign.name)
            continue

        keyword = (
            random.choice(campaign.target_keywords)
            if campaign.target_keywords
            else _domain_from_target(campaign.target_url)
        )

        def _make_job(job_type: JobType, term: str = "") -> Job:
            return Job(
                job_type=job_type,
                campaign_name=campaign.name,
                random_browse_terms=campaign.random_browse_terms,
                rank_page_terms=campaign.rank_page_terms,
                target_url=campaign.target_url,
                search_term=term or keyword,
                target_keywords=campaign.target_keywords,
                external_target_urls=campaign.external_target_urls,
                scheduled_at=start_time + random.uniform(0, run_seconds),
            )

        for _ in range(campaign.jobs.direct_visit):
            jobs.append(_make_job(JobType.DIRECT_VISIT))

        for _ in range(campaign.jobs.search_navigate):
            jobs.append(_make_job(JobType.SEARCH_NAVIGATE, keyword))

        for _ in range(campaign.jobs.suggested_click):
            jobs.append(_make_job(JobType.SUGGESTED_CLICK))

        for _ in range(campaign.jobs.target_direct):
            jobs.append(_make_job(JobType.TARGET_DIRECT, keyword))

    jobs.sort(key=lambda j: j.scheduled_at)
    random.shuffle(jobs)
    jobs.sort(key=lambda j: j.scheduled_at)
    return jobs


def _domain_from_target(target_url: str) -> str:
    import re

    match = re.search(r"/review/([^/?#]+)", target_url)
    return match.group(1) if match else target_url


def execute_job(job: Job, settings: Settings, proxy: str | None) -> JobResult:
    device = random.choice(DESKTOP_PROFILES) if job.job_type != JobType.DIRECT_VISIT else random_device()
    logger.info(
        "Executing %s | campaign=%s | device=%s",
        job.job_type.value,
        job.campaign_name,
        device.name,
    )

    base = JobResult(
        success=False,
        job_type=job.job_type.value,
        campaign_name=job.campaign_name,
        target_url=job.target_url,
        device=device.name,
    )

    try:
        if proxy:
            logger.info("Proxy active for this job")
        with browser_session(
            headless=settings.headless,
            proxy=proxy,
            device=device,
            trustpilot_locale=settings.trustpilot_locale,
        ) as (_, _, _, page):
            journey_kwargs = dict(
                page=page,
                locale=settings.trustpilot_locale,
                random_terms=job.random_browse_terms,
                rank_terms=job.rank_page_terms,
                trustpilot_target=job.target_url,
                target_keywords=job.target_keywords,
                external_urls=job.external_target_urls,
                search_term=job.search_term,
                min_depth=settings.min_journey_depth,
                max_depth=settings.max_journey_depth,
                min_duration=settings.min_page_duration,
                max_duration=settings.max_page_duration,
                click_external=settings.click_out_external,
            )

            if job.job_type == JobType.SUGGESTED_CLICK:
                outcome = journey.run_search_journey(**journey_kwargs, prefer_suggested=True)
            else:
                outcome = journey.run_search_journey(**journey_kwargs)

            base.success = outcome.success
            base.list_b_page = outcome.rank_page_term
            base.list_b_url = outcome.rank_page_url
            base.target_reached = outcome.target_reached
            base.final_url = outcome.final_url or page.url
            base.error = outcome.error

    except Exception as exc:
        logger.error("Job execution error (%s): %s", job.job_type.value, exc)
        base.error = str(exc)

    return base
