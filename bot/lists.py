"""Load client list files and derive Trustpilot search terms."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


def load_lines(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    return [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def url_to_search_term(url: str) -> str:
    """Extract a search term from a Trustpilot review URL."""
    match = re.search(r"/review/([^/?#]+)", url)
    if match:
        return match.group(1)
    host = urlparse(url).netloc.replace("www.", "")
    return host or url


def terms_from_file(path: str | Path) -> list[str]:
    """Load a list file and return search terms (from URLs or plain text)."""
    terms: list[str] = []
    seen: set[str] = set()
    for line in load_lines(path):
        term = url_to_search_term(line) if "trustpilot.com" in line else line
        key = term.lower().strip()
        if key and key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def keywords_from_target_file(path: str | Path) -> tuple[str, list[str]]:
    """Load target file — first Trustpilot URL + all lines as keywords."""
    lines = load_lines(path)
    target_url = ""
    keywords: list[str] = []
    seen: set[str] = set()

    for line in lines:
        if "trustpilot.com/review/" in line and not target_url:
            target_url = line.split("#")[0].strip()
        term = url_to_search_term(line) if "trustpilot.com" in line else line
        key = term.lower().strip()
        if key and key not in seen:
            seen.add(key)
            keywords.append(term)

    return target_url, keywords
