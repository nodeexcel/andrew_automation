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
from bot import trustpilot

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
    source_url: str
    target_url: str
    search_term: str
    target_keywords: list[str]
    scheduled_at: float  # unix timestamp


def build_job_queue(campaigns: list[Campaign], run_duration_hours: float) -> list[Job]:
    """
    Build a shuffled queue of all jobs spread across the run duration.
    Each job gets a random scheduled time within the period.
    """
    jobs: list[Job] = []
    run_seconds = run_duration_hours * 3600
    start_time = time.time()

    for campaign in campaigns:
        if not campaign.enabled:
            continue

        if not campaign.source_urls and campaign.jobs.direct_visit + campaign.jobs.suggested_click + campaign.jobs.search_navigate > 0:
            logger.warning("Campaign '%s' has no source URLs", campaign.name)
            continue

        for _ in range(campaign.jobs.direct_visit):
            source = random.choice(campaign.source_urls)
            jobs.append(
                Job(
                    job_type=JobType.DIRECT_VISIT,
                    campaign_name=campaign.name,
                    source_url=source,
                    target_url=campaign.target_url,
                    search_term="",
                    target_keywords=campaign.target_keywords,
                    scheduled_at=start_time + random.uniform(0, run_seconds),
                )
            )

        for _ in range(campaign.jobs.search_navigate):
            source = random.choice(campaign.source_urls)
            keyword = random.choice(campaign.target_keywords) if campaign.target_keywords else _domain_from_target(campaign.target_url)
            jobs.append(
                Job(
                    job_type=JobType.SEARCH_NAVIGATE,
                    campaign_name=campaign.name,
                    source_url=source,
                    target_url=campaign.target_url,
                    search_term=keyword,
                    target_keywords=campaign.target_keywords,
                    scheduled_at=start_time + random.uniform(0, run_seconds),
                )
            )

        for _ in range(campaign.jobs.suggested_click):
            source = random.choice(campaign.source_urls)
            jobs.append(
                Job(
                    job_type=JobType.SUGGESTED_CLICK,
                    campaign_name=campaign.name,
                    source_url=source,
                    target_url=campaign.target_url,
                    search_term="",
                    target_keywords=campaign.target_keywords,
                    scheduled_at=start_time + random.uniform(0, run_seconds),
                )
            )

        for _ in range(campaign.jobs.target_direct):
            jobs.append(
                Job(
                    job_type=JobType.TARGET_DIRECT,
                    campaign_name=campaign.name,
                    source_url="",
                    target_url=campaign.target_url,
                    search_term="",
                    target_keywords=campaign.target_keywords,
                    scheduled_at=start_time + random.uniform(0, run_seconds),
                )
            )

    jobs.sort(key=lambda j: j.scheduled_at)
    random.shuffle(jobs)
    jobs.sort(key=lambda j: j.scheduled_at)
    return jobs


def _domain_from_target(target_url: str) -> str:
    import re

    match = re.search(r"/review/([^/?#]+)", target_url)
    return match.group(1) if match else target_url


def execute_job(
    job: Job,
    settings: Settings,
    proxy: str | None,
) -> bool:
    """Execute a single job in its own browser session."""
    # Search navigation works most reliably on desktop layouts
    if job.job_type == JobType.SEARCH_NAVIGATE:
        device = random.choice(DESKTOP_PROFILES)
    else:
        device = random_device()
    logger.info(
        "Executing %s | campaign=%s | device=%s",
        job.job_type.value,
        job.campaign_name,
        device.name,
    )

    try:
        with browser_session(
            headless=settings.headless,
            proxy=proxy,
            device=device,
        ) as (_, _, _, page):
            if job.job_type == JobType.DIRECT_VISIT:
                return trustpilot.visit_url(
                    page,
                    job.source_url,
                    settings.min_page_duration,
                    settings.max_page_duration,
                )

            if job.job_type == JobType.SEARCH_NAVIGATE:
                return trustpilot.search_and_navigate(
                    page,
                    job.source_url,
                    job.search_term,
                    job.target_url,
                    job.target_keywords,
                    settings.min_page_duration,
                    settings.max_page_duration,
                )

            if job.job_type == JobType.SUGGESTED_CLICK:
                return trustpilot.click_suggested_website(
                    page,
                    job.source_url,
                    job.target_url,
                    job.target_keywords,
                    settings.min_page_duration,
                    settings.max_page_duration,
                )

            if job.job_type == JobType.TARGET_DIRECT:
                return trustpilot.visit_url(
                    page,
                    job.target_url,
                    settings.min_page_duration,
                    settings.max_page_duration,
                )

    except Exception as exc:
        logger.error("Job execution error (%s): %s", job.job_type.value, exc)
        return False

    return False
