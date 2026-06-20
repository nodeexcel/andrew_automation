"""CSV job result reporting."""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CSV_COLUMNS = [
    "time",
    "job_type",
    "campaign",
    "list_b_page",
    "list_b_url",
    "target_url",
    "target_reached",
    "final_url",
    "success",
    "device",
    "error",
]


@dataclass
class JobResult:
    success: bool
    job_type: str
    campaign_name: str
    list_b_page: str = ""
    list_b_url: str = ""
    target_url: str = ""
    target_reached: bool = False
    final_url: str = ""
    device: str = ""
    error: str = ""


class CsvReporter:
    """Thread-safe CSV writer — one row per job."""

    def __init__(self, csv_path: str):
        self.path = Path(csv_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(CSV_COLUMNS)

    def write(self, result: JobResult) -> None:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            result.job_type,
            result.campaign_name,
            result.list_b_page,
            result.list_b_url,
            result.target_url,
            "yes" if result.target_reached else "no",
            result.final_url,
            "success" if result.success else "fail",
            result.device,
            result.error,
        ]
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(row)
            self._sync_excel()

    def _sync_excel(self) -> None:
        try:
            from bot.export import sync_xlsx

            sync_xlsx(self.path)
        except Exception:
            pass
