"""24-hour job scheduler with multithreaded workers."""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bot.config import Config
from bot.jobs import Job, build_job_queue, execute_job

logger = logging.getLogger("trustpilot_bot")


class Scheduler:
    """Runs jobs continuously over a configurable period with multiple workers."""

    def __init__(self, config: Config):
        self.config = config
        self.settings = config.settings
        self._proxy_index = 0
        self._proxy_lock = threading.Lock()
        self._stats = {"completed": 0, "failed": 0, "skipped": 0}
        self._stats_lock = threading.Lock()

    def _next_proxy(self) -> str | None:
        if not self.config.proxies:
            return None
        with self._proxy_lock:
            proxy = self.config.proxies[self._proxy_index % len(self.config.proxies)]
            self._proxy_index += 1
            return proxy

    def _wait_for_schedule(self, job: Job) -> bool:
        """Wait until the job's scheduled time. Returns False if run period ended."""
        now = time.time()
        run_end = self._start_time + self.settings.run_duration_hours * 3600

        if job.scheduled_at > now:
            wait = job.scheduled_at - now
            if now + wait > run_end:
                return False
            logger.debug("Waiting %.0fs until scheduled job", wait)
            time.sleep(wait)

        return time.time() < run_end

    def _post_job_delay(self) -> None:
        """Variable delay between tasks to avoid hammering the same proxy."""
        delay = random.uniform(
            self.settings.min_task_interval,
            self.settings.max_task_interval,
        )
        logger.debug("Post-job delay: %.0fs", delay)
        time.sleep(delay)

    def _record_result(self, success: bool) -> None:
        with self._stats_lock:
            if success:
                self._stats["completed"] += 1
            else:
                self._stats["failed"] += 1

    def _worker(self, worker_id: int, jobs: list[Job]) -> None:
        """Worker thread: processes assigned jobs with delays."""
        thread_name = f"Worker-{worker_id}"
        threading.current_thread().name = thread_name

        my_jobs = [j for i, j in enumerate(jobs) if i % self.settings.max_workers == worker_id - 1]
        logger.info("%s assigned %d jobs", thread_name, len(my_jobs))

        run_end = self._start_time + self.settings.run_duration_hours * 3600

        for job in my_jobs:
            if time.time() >= run_end:
                with self._stats_lock:
                    self._stats["skipped"] += len(my_jobs) - my_jobs.index(job)
                break

            if not self._wait_for_schedule(job):
                with self._stats_lock:
                    self._stats["skipped"] += 1
                continue

            proxy = self._next_proxy()
            success = execute_job(job, self.settings, proxy)
            self._record_result(success)

            if time.time() < run_end:
                self._post_job_delay()

    def run(self) -> dict:
        """Start the scheduler and run for the configured duration."""
        enabled_campaigns = [c for c in self.config.campaigns if c.enabled]
        if not enabled_campaigns:
            logger.error("No enabled campaigns found in config")
            return self._stats

        jobs = build_job_queue(enabled_campaigns, self.settings.run_duration_hours)
        if not jobs:
            logger.error("No jobs generated — check job counts in config")
            return self._stats

        total_jobs = len(jobs)
        self._start_time = time.time()
        run_end = self._start_time + self.settings.run_duration_hours * 3600

        logger.info("=" * 60)
        logger.info("Trustpilot Bot starting")
        logger.info("Duration: %.1f hours | Workers: %d | Jobs: %d", self.settings.run_duration_hours, self.settings.max_workers, total_jobs)
        logger.info("Proxies: %d configured", len(self.config.proxies))
        logger.info("Campaigns: %s", ", ".join(c.name for c in enabled_campaigns))
        logger.info("=" * 60)

        for job_type_count in _job_type_summary(jobs):
            logger.info("  %s", job_type_count)

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            futures = [
                executor.submit(self._worker, i + 1, jobs)
                for i in range(self.settings.max_workers)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    logger.error("Worker crashed: %s", exc)

        elapsed = time.time() - self._start_time
        logger.info("=" * 60)
        logger.info("Run complete in %.1f hours", elapsed / 3600)
        logger.info("Completed: %d | Failed: %d | Skipped: %d", self._stats["completed"], self._stats["failed"], self._stats["skipped"])
        logger.info("=" * 60)

        return dict(self._stats)


def _job_type_summary(jobs: list[Job]) -> list[str]:
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.job_type.value] = counts.get(job.job_type.value, 0) + 1
    return [f"{k}: {v}" for k, v in sorted(counts.items())]
