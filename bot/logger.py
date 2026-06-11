"""Logging setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(log_file: str, level: int = logging.INFO) -> logging.Logger:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("trustpilot_bot")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
