"""Journey outcome data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JourneyResult:
    success: bool
    rank_page_term: str = ""
    rank_page_url: str = ""
    target_reached: bool = False
    final_url: str = ""
    external_clicked: bool = False
    error: str = ""
