"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class JobCounts:
    direct_visit: int = 0
    search_navigate: int = 0
    suggested_click: int = 0
    target_direct: int = 0

    @property
    def total(self) -> int:
        return (
            self.direct_visit
            + self.search_navigate
            + self.suggested_click
            + self.target_direct
        )


@dataclass
class Campaign:
    name: str
    enabled: bool
    source_urls: list[str]
    target_url: str
    target_keywords: list[str]
    jobs: JobCounts


@dataclass
class Settings:
    run_duration_hours: float = 24.0
    min_page_duration: int = 25
    max_page_duration: int = 90
    min_task_interval: int = 180
    max_task_interval: int = 900
    max_workers: int = 3
    headless: bool = True
    trustpilot_locale: str = "de"
    log_file: str = "logs/bot.log"


@dataclass
class Config:
    settings: Settings
    campaigns: list[Campaign]
    proxies: list[str] = field(default_factory=list)


def _load_proxies(data: dict[str, Any], config_dir: Path) -> list[str]:
    proxies_section = data.get("proxies", {})
    if isinstance(proxies_section, list):
        return [p.strip() for p in proxies_section if p.strip()]

    proxy_file = proxies_section.get("file")
    if proxy_file:
        path = config_dir / proxy_file
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            return [line.strip() for line in lines if line.strip() and not line.startswith("#")]

    inline = proxies_section.get("list", [])
    return [p.strip() for p in inline if p.strip()]


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    settings_data = data.get("settings", {})
    settings = Settings(
        run_duration_hours=float(settings_data.get("run_duration_hours", 24)),
        min_page_duration=int(settings_data.get("min_page_duration", 25)),
        max_page_duration=int(settings_data.get("max_page_duration", 90)),
        min_task_interval=int(settings_data.get("min_task_interval", 180)),
        max_task_interval=int(settings_data.get("max_task_interval", 900)),
        max_workers=int(settings_data.get("max_workers", 3)),
        headless=bool(settings_data.get("headless", True)),
        trustpilot_locale=str(settings_data.get("trustpilot_locale", "de")),
        log_file=str(settings_data.get("log_file", "logs/bot.log")),
    )

    campaigns: list[Campaign] = []
    for c in data.get("campaigns", []):
        jobs_data = c.get("jobs", {})
        campaigns.append(
            Campaign(
                name=c.get("name", "unnamed"),
                enabled=bool(c.get("enabled", True)),
                source_urls=list(c.get("source_urls", [])),
                target_url=str(c.get("target_url", "")),
                target_keywords=list(c.get("target_keywords", [])),
                jobs=JobCounts(
                    direct_visit=int(jobs_data.get("direct_visit", 0)),
                    search_navigate=int(jobs_data.get("search_navigate", 0)),
                    suggested_click=int(jobs_data.get("suggested_click", 0)),
                    target_direct=int(jobs_data.get("target_direct", 0)),
                ),
            )
        )

    proxies = _load_proxies(data, config_path.parent)

    return Config(settings=settings, campaigns=campaigns, proxies=proxies)


def get_config_path() -> Path:
    env_path = os.getenv("BOT_CONFIG")
    if env_path:
        return Path(env_path)
    if Path("config.yaml").exists():
        return Path("config.yaml")
    return Path("config.example.yaml")
