#!/usr/bin/env python3
"""
Trustpilot Automation Bot

Visits Trustpilot pages, searches for target websites, clicks suggested
businesses, and runs continuously over a 24-hour period with proxy support,
device emulation, and multithreaded workers.

Usage:
    python main.py                    # uses config.yaml
    python main.py --config my.yaml   # custom config
    python main.py --dry-run          # show planned jobs without running
"""

from __future__ import annotations

import argparse
import sys

from bot.config import get_config_path, load_config
from bot.jobs import Job, JobType, build_job_queue, execute_job
from bot.logger import setup_logger
from bot.scheduler import Scheduler, _job_type_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trustpilot automation bot")
    parser.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to config YAML (default: config.yaml or config.example.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned jobs and exit without running browsers",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run one quick test of each job type for the first enabled campaign",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config or str(get_config_path())

    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Copy config.example.yaml to config.yaml and customize it.", file=sys.stderr)
        return 1

    logger = setup_logger(config.settings.log_file)

    enabled = [c for c in config.campaigns if c.enabled]
    if not enabled:
        logger.error("No enabled campaigns in %s", config_path)
        return 1

    if args.test:
        campaign = enabled[0]
        if not campaign.source_urls:
            logger.error("First campaign has no source URLs")
            return 1
        source = campaign.source_urls[0]
        keyword = campaign.target_keywords[0] if campaign.target_keywords else campaign.target_url
        config.settings.headless = False
        config.settings.min_page_duration = 8
        config.settings.max_page_duration = 15
        config.settings.min_journey_depth = 3
        config.settings.max_journey_depth = 5
        ext = campaign.external_target_urls
        tests = [
            Job(JobType.DIRECT_VISIT, campaign.name, source, campaign.target_url, "", campaign.target_keywords, ext, 0),
            Job(JobType.SEARCH_NAVIGATE, campaign.name, source, campaign.target_url, keyword, campaign.target_keywords, ext, 0),
            Job(JobType.SUGGESTED_CLICK, campaign.name, source, campaign.target_url, "", campaign.target_keywords, ext, 0),
            Job(JobType.TARGET_DIRECT, campaign.name, "", campaign.target_url, "", campaign.target_keywords, ext, 0),
        ]
        logger.info("Running quick test of all 4 job types (browser visible)...")
        results = {}
        for job in tests:
            logger.info("--- Testing %s ---", job.job_type.value)
            results[job.job_type.value] = execute_job(job, config.settings, None)
        print("\nTest results:")
        for name, ok in results.items():
            print(f"  {name}: {'PASS' if ok else 'FAIL'}")
        return 0 if all(results.values()) else 1

    if args.dry_run:
        jobs = build_job_queue(enabled, config.settings.run_duration_hours)
        print(f"\nDry run — {len(jobs)} jobs planned over {config.settings.run_duration_hours}h\n")
        for line in _job_type_summary(jobs):
            print(f"  {line}")
        print()
        for campaign in enabled:
            print(f"Campaign: {campaign.name}")
            print(f"  Sources: {len(campaign.source_urls)} URLs")
            print(f"  Target:  {campaign.target_url}")
            print(f"  Keywords: {campaign.target_keywords}")
            print(f"  Jobs: {campaign.jobs.total} total")
            print()
        print(f"Workers: {config.settings.max_workers}")
        print(f"Proxies: {len(config.proxies)}")
        return 0

    scheduler = Scheduler(config)
    stats = scheduler.run()

    if stats["completed"] == 0 and stats["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
