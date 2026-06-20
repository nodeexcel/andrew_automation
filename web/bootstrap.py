"""First-run setup so clients only need to open the web app."""

from __future__ import annotations

import shutil
from pathlib import Path

from bot.config import load_config_yaml, save_config_yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TARGET = """https://www.trustpilot.com/review/your-site.com
your-site.com
"""

DEFAULT_LIST_A = """https://www.trustpilot.com/review/example-source.com
"""

DEFAULT_LIST_B = """https://www.trustpilot.com/review/example-rank-page.com
"""

DEFAULT_PROXIES = """# Add one proxy per line (recommended for production)
# http://username:password@proxy.example.com:8080
"""


def ensure_setup() -> Path:
    """Create config, folders, and starter list files if missing."""
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
    (PROJECT_ROOT / "lists").mkdir(exist_ok=True)

    config_path = PROJECT_ROOT / "config.yaml"
    example_path = PROJECT_ROOT / "config.example.yaml"

    if not config_path.exists():
        if example_path.exists():
            shutil.copy(example_path, config_path)
        else:
            save_config_yaml(config_path, _default_config())

    _ensure_file(PROJECT_ROOT / "lists" / "list_a.txt", DEFAULT_LIST_A)
    _ensure_file(PROJECT_ROOT / "lists" / "list_b.txt", DEFAULT_LIST_B)
    _ensure_file(PROJECT_ROOT / "lists" / "target.txt", DEFAULT_TARGET)
    _ensure_file(PROJECT_ROOT / "proxies.txt", DEFAULT_PROXIES)

    return config_path.resolve()


def _ensure_file(path: Path, content: str) -> None:
    if not path.exists() or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")


def _default_config() -> dict:
    return {
        "settings": {
            "run_duration_hours": 24,
            "min_page_duration": 25,
            "max_page_duration": 90,
            "min_task_interval": 180,
            "max_task_interval": 900,
            "max_workers": 3,
            "headless": True,
            "trustpilot_locale": "www",
            "log_file": "logs/bot.log",
            "csv_file": "logs/results.csv",
            "min_journey_depth": 10,
            "max_journey_depth": 15,
            "click_out_external": True,
        },
        "proxies": {"file": "proxies.txt"},
        "campaigns": [
            {
                "name": "My campaign",
                "enabled": True,
                "lists": {
                    "random_browse_file": "lists/list_a.txt",
                    "rank_pages_file": "lists/list_b.txt",
                    "target_file": "lists/target.txt",
                },
                "jobs": {
                    "direct_visit": 20,
                    "search_navigate": 30,
                    "suggested_click": 15,
                    "target_direct": 10,
                },
            }
        ],
    }
