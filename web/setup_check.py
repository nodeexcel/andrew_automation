"""Validate that the bot is ready to run — used by the dashboard."""

from __future__ import annotations

from pathlib import Path

from bot.config import campaign_list_paths, load_config
from bot.lists import terms_from_file


def check_readiness(config_path: Path) -> dict:
    """
    Return setup status for the web UI.

    issues: blocking problems (must fix before start)
    warnings: recommended fixes (bot can still run)
    ready: True when no blocking issues
    """
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    try:
        config = load_config(config_path)
    except Exception as exc:
        issues.append(
            {
                "message": str(exc),
                "fix_label": "Open Campaign",
                "fix_url": "campaign",
            }
        )
        return {"ready": False, "issues": issues, "warnings": warnings}

    enabled = [c for c in config.campaigns if c.enabled]
    if not enabled:
        issues.append(
            {
                "message": "No campaign is enabled. Turn on at least one campaign.",
                "fix_label": "Open Campaign",
                "fix_url": "campaign",
            }
        )

    if not config.proxies:
        warnings.append(
            {
                "message": "No proxies configured — the bot will use your real IP address.",
                "fix_label": "Add proxies",
                "fix_url": "proxies",
            }
        )

    for campaign in enabled:
        prefix = f"Campaign “{campaign.name}”: "

        if not campaign.random_browse_terms:
            issues.append(
                {
                    "message": prefix + "Browse list (List A) is empty.",
                    "fix_label": "Edit browse list",
                    "fix_url": "lists",
                }
            )

        if not campaign.rank_page_terms:
            warnings.append(
                {
                    "message": prefix + "Rank pages list (List B) is empty.",
                    "fix_label": "Edit rank pages",
                    "fix_url": "lists",
                }
            )

        if not campaign.target_url or "your-site.com" in campaign.target_url:
            issues.append(
                {
                    "message": prefix + "Set your target Trustpilot review page.",
                    "fix_label": "Set target",
                    "fix_url": "campaign",
                }
            )

        if not campaign.target_keywords:
            issues.append(
                {
                    "message": prefix + "Add at least one search keyword for your target.",
                    "fix_label": "Set keywords",
                    "fix_url": "campaign",
                }
            )

        if campaign.jobs.total == 0:
            issues.append(
                {
                    "message": prefix + "Job counts are all zero — nothing will run.",
                    "fix_label": "Set job counts",
                    "fix_url": "campaign",
                }
            )

    return {
        "ready": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def write_target_file(path: Path, target_url: str, keywords: list[str]) -> None:
    """Write target list file from campaign form fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [target_url.strip()]
    seen = {target_url.lower().strip()}
    for kw in keywords:
        key = kw.strip().lower()
        if key and key not in seen:
            seen.add(key)
            lines.append(kw.strip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_target_for_form(path: Path) -> tuple[str, list[str]]:
    """Load target URL and keyword lines (excluding the URL line) for the form."""
    from bot.lists import load_lines, normalize_trustpilot_review_url

    target_url = ""
    keywords: list[str] = []
    for line in load_lines(path):
        if "trustpilot.com" in line and not target_url:
            target_url = normalize_trustpilot_review_url(line)
        else:
            keywords.append(line)
    return target_url, keywords
