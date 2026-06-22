"""Flask web interface for the Trustpilot bot."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for

from bot.config import (
    campaign_list_paths,
    get_config_path,
    load_config,
    load_config_yaml,
    save_config_yaml,
)
from bot.jobs import build_job_queue
from bot.export import sync_xlsx
from bot.scheduler import _job_type_summary
from web.bootstrap import ensure_setup
from web.bot_runner import PROJECT_ROOT, runner
from web.setup_check import check_readiness, read_target_for_form, write_target_file

LIST_LABELS = {
    "list_a": (
        "Browse list (List A)",
        "Trustpilot pages or search terms for random browsing — one per line.",
    ),
    "list_b": (
        "Rank pages (List B)",
        "Trustpilot pages you want your target to appear on — one per line.",
    ),
}


def create_app() -> Flask:
    ensure_setup()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = os.getenv("BOT_UI_SECRET", "trustpilot-bot-local-dev")

    def _config_path() -> Path:
        path = get_config_path()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def _read_text_file(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _write_text_file(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _proxy_file(config_path: Path, raw: dict) -> Path:
        proxies_section = raw.get("proxies", {})
        if isinstance(proxies_section, dict):
            rel = proxies_section.get("file", "proxies.txt")
            return config_path.parent / rel
        return config_path.parent / "proxies.txt"

    def _dashboard_stats(config_path: Path) -> dict:
        try:
            config = load_config(config_path)
        except Exception:
            return {}

        enabled = [c for c in config.campaigns if c.enabled]
        jobs = build_job_queue(enabled, config.settings.run_duration_hours) if enabled else []

        csv_path = config_path.parent / config.settings.csv_file
        rows: list[dict[str, str]] = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        return {
            "campaign_count": len(config.campaigns),
            "enabled_count": len(enabled),
            "job_count": len(jobs),
            "job_summary": _job_type_summary(jobs),
            "proxy_count": len(config.proxies),
            "total_runs": len(rows),
            "recent_results": list(reversed(rows[-8:])),
        }

    def _default_campaign() -> dict:
        return {
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

    @app.context_processor
    def inject_globals():
        return {
            "bot_running": runner.is_running(),
            "nav_items": [
                ("dashboard", "Dashboard", "home"),
                ("campaign", "Campaign", "target"),
                ("lists", "Browse Lists", "list"),
                ("proxies", "Proxies", "shield"),
                ("settings", "Settings", "sliders"),
                ("results", "Results", "bar-chart"),
                ("logs", "Logs", "file-text"),
            ],
        }

    @app.route("/")
    def dashboard():
        config_path = _config_path()
        stats = _dashboard_stats(config_path)
        setup = check_readiness(config_path)
        show_output = request.args.get("output") == "1"
        return render_template(
            "dashboard.html",
            stats=stats,
            setup=setup,
            command_output=runner.last_output if show_output else "",
        )

    @app.route("/api/status")
    def api_status():
        config_path = _config_path()
        stats = _dashboard_stats(config_path)
        setup = check_readiness(config_path)
        return jsonify({
            "running": runner.is_running(),
            "ready": setup["ready"],
            **stats,
        })

    @app.post("/bot/start")
    def bot_start():
        config_path = _config_path()
        setup = check_readiness(config_path)
        if not setup["ready"]:
            flash("Complete the setup checklist before starting the bot.", "error")
            return redirect(url_for("dashboard"))
        ok, msg = runner.start(str(config_path))
        flash(msg, "success" if ok else "error")
        return redirect(url_for("dashboard"))

    @app.post("/bot/stop")
    def bot_stop():
        ok, msg = runner.stop()
        flash(msg, "success" if ok else "error")
        return redirect(url_for("dashboard"))

    @app.post("/bot/dry-run")
    def bot_dry_run():
        config_path = _config_path()
        setup = check_readiness(config_path)
        if not setup["ready"]:
            flash("Complete the setup checklist first.", "error")
            return redirect(url_for("dashboard"))
        ok, output = runner.dry_run(str(config_path))
        if not ok and not output:
            flash("Preview failed.", "error")
            return redirect(url_for("dashboard"))
        flash("Schedule preview ready." if ok else "Preview finished with issues.", "success" if ok else "error")
        return redirect(url_for("dashboard", output=1))

    @app.post("/bot/test")
    def bot_test():
        if runner.is_running():
            flash("Stop the bot before running a test.", "error")
            return redirect(url_for("dashboard"))
        config_path = _config_path()
        setup = check_readiness(config_path)
        if not setup["ready"]:
            flash("Complete the setup checklist first.", "error")
            return redirect(url_for("dashboard"))
        ok, _output = runner.test_run(str(config_path))
        flash("Test passed — check Results for details." if ok else "Test finished with some failures — check Results.", "success" if ok else "error")
        return redirect(url_for("results"))

    @app.post("/bot/check-proxy")
    def bot_check_proxy():
        if runner.is_running():
            flash("Stop the bot before testing proxies.", "error")
            return redirect(url_for("proxies"))
        config_path = _config_path()
        try:
            config = load_config(config_path)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("proxies"))
        if not config.proxies:
            flash("Add at least one proxy first.", "error")
            return redirect(url_for("proxies"))
        ok, output = runner.check_proxy(str(config_path))
        flash("Proxy test complete." if ok else "Proxy test failed.", "success" if ok else "error")
        return redirect(url_for("proxies", output=1))

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)

        if request.method == "POST":
            settings_data = raw.setdefault("settings", {})
            settings_data["run_duration_hours"] = float(request.form.get("run_duration_hours", 24))
            settings_data["min_page_duration"] = int(request.form.get("min_page_duration", 25))
            settings_data["max_page_duration"] = int(request.form.get("max_page_duration", 90))
            settings_data["min_task_interval"] = int(request.form.get("min_task_interval", 180))
            settings_data["max_task_interval"] = int(request.form.get("max_task_interval", 900))
            settings_data["max_workers"] = int(request.form.get("max_workers", 3))
            settings_data["headless"] = request.form.get("headless") == "on"
            settings_data["trustpilot_locale"] = request.form.get("trustpilot_locale", "www").strip()
            settings_data["min_journey_depth"] = int(request.form.get("min_journey_depth", 10))
            settings_data["max_journey_depth"] = int(request.form.get("max_journey_depth", 15))
            settings_data["click_out_external"] = request.form.get("click_out_external") == "on"

            save_config_yaml(config_path, raw)
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))

        return render_template("settings.html", settings=raw.get("settings", {}))

    @app.route("/campaign", methods=["GET", "POST"])
    def campaign():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)
        campaigns = raw.setdefault("campaigns", [])

        if not campaigns:
            campaigns.append(_default_campaign())

        index = min(int(request.args.get("i", 0)), len(campaigns) - 1)
        current = campaigns[index]
        paths = campaign_list_paths(current, config_path)
        target_url, target_keywords = read_target_for_form(paths["target"])
        external_urls = current.get("external_target_urls") or []

        if request.method == "POST":
            current["name"] = request.form.get("name", "Campaign").strip()
            current["enabled"] = request.form.get("enabled") == "on"

            url = request.form.get("target_url", "").strip()
            keywords = [
                line.strip()
                for line in request.form.get("target_keywords", "").splitlines()
                if line.strip()
            ]
            write_target_file(paths["target"], url, keywords)

            current.pop("target_url", None)
            current.pop("target_keywords", None)

            external = [
                line.strip()
                for line in request.form.get("external_urls", "").splitlines()
                if line.strip()
            ]
            if external:
                current["external_target_urls"] = external
            else:
                current.pop("external_target_urls", None)

            jobs = current.setdefault("jobs", {})
            jobs["direct_visit"] = int(request.form.get("direct_visit", 0))
            jobs["search_navigate"] = int(request.form.get("search_navigate", 0))
            jobs["suggested_click"] = int(request.form.get("suggested_click", 0))
            jobs["target_direct"] = int(request.form.get("target_direct", 0))

            save_config_yaml(config_path, raw)
            flash("Campaign saved.", "success")
            return redirect(url_for("campaign", i=index))

        preview = {}
        try:
            config = load_config(config_path)
            if index < len(config.campaigns):
                c = config.campaigns[index]
                preview = {
                    "target_url": c.target_url,
                    "target_keywords": c.target_keywords,
                    "list_a_count": len(c.random_browse_terms),
                    "list_b_count": len(c.rank_page_terms),
                    "total_jobs": c.jobs.total,
                }
        except Exception as exc:
            preview = {"error": str(exc)}

        return render_template(
            "campaign.html",
            campaign=current,
            index=index,
            campaigns=campaigns,
            target_url=target_url,
            target_keywords="\n".join(target_keywords),
            external_urls="\n".join(external_urls),
            preview=preview,
        )

    @app.post("/campaign/add")
    def campaign_add():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)
        campaigns = raw.setdefault("campaigns", [])
        n = len(campaigns) + 1
        slug = f"campaign_{n}"
        campaigns.append(
            {
                "name": f"Campaign {n}",
                "enabled": True,
                "lists": {
                    "random_browse_file": f"lists/{slug}_list_a.txt",
                    "rank_pages_file": f"lists/{slug}_list_b.txt",
                    "target_file": f"lists/{slug}_target.txt",
                },
                "jobs": {
                    "direct_visit": 10,
                    "search_navigate": 15,
                    "suggested_click": 5,
                    "target_direct": 5,
                },
            }
        )
        save_config_yaml(config_path, raw)
        new_campaign = campaigns[-1]
        paths = campaign_list_paths(new_campaign, config_path)
        _write_text_file(paths["list_a"], "")
        _write_text_file(paths["list_b"], "")
        write_target_file(
            paths["target"],
            "https://www.trustpilot.com/review/your-site.com",
            ["your-site.com"],
        )
        flash("New campaign created.", "success")
        return redirect(url_for("campaign", i=len(campaigns) - 1))

    @app.post("/campaign/delete")
    def campaign_delete():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)
        campaigns = raw.get("campaigns", [])
        if len(campaigns) <= 1:
            flash("You need at least one campaign.", "error")
            return redirect(url_for("campaign"))
        index = min(int(request.form.get("index", 0)), len(campaigns) - 1)
        name = campaigns[index].get("name", "Campaign")
        campaigns.pop(index)
        save_config_yaml(config_path, raw)
        flash(f"Deleted “{name}”.", "success")
        return redirect(url_for("campaign", i=max(0, index - 1)))

    @app.route("/lists", methods=["GET", "POST"])
    def lists():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)
        campaigns = raw.get("campaigns", [])
        if not campaigns:
            flash("Set up your campaign first.", "error")
            return redirect(url_for("campaign"))

        index = min(int(request.args.get("i", 0)), len(campaigns) - 1)
        list_key = request.args.get("list", "list_a")
        if list_key not in LIST_LABELS:
            list_key = "list_a"

        paths = campaign_list_paths(campaigns[index], config_path)
        file_path = paths[list_key]
        label, hint = LIST_LABELS[list_key]

        if request.method == "POST":
            content = request.form.get("content", "")
            _write_text_file(file_path, content)
            flash(f"{label} saved.", "success")
            return redirect(url_for("lists", i=index, list=list_key))

        return render_template(
            "lists.html",
            content=_read_text_file(file_path),
            list_key=list_key,
            label=label,
            hint=hint,
            index=index,
            campaigns=campaigns,
            campaign_name=campaigns[index].get("name", "Campaign"),
        )

    @app.route("/proxies", methods=["GET", "POST"])
    def proxies():
        config_path = _config_path()
        _, raw = load_config_yaml(config_path)
        proxy_path = _proxy_file(config_path, raw)
        show_output = request.args.get("output") == "1"

        if request.method == "POST":
            content = request.form.get("content", "")
            _write_text_file(proxy_path, content)
            flash("Proxies saved.", "success")
            return redirect(url_for("proxies"))

        loaded = []
        try:
            config = load_config(config_path)
            loaded = config.proxies
        except Exception:
            pass

        return render_template(
            "proxies.html",
            content=_read_text_file(proxy_path),
            loaded_count=len(loaded),
            command_output=runner.last_output if show_output else "",
        )

    @app.route("/results")
    def results():
        config_path = _config_path()
        try:
            config = load_config(config_path)
            csv_path = config_path.parent / config.settings.csv_file
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

        rows: list[dict[str, str]] = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

        rows.reverse()
        success = sum(1 for r in rows if r.get("success") == "success")
        return render_template(
            "results.html",
            rows=rows,
            total=len(rows),
            success=success,
            has_excel=csv_path.exists() and len(rows) > 0,
        )

    @app.route("/results/download")
    def results_download():
        config_path = _config_path()
        try:
            config = load_config(config_path)
            csv_path = config_path.parent / config.settings.csv_file
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("results"))

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            flash("No results to download yet. Run the bot first.", "error")
            return redirect(url_for("results"))

        try:
            xlsx_path = sync_xlsx(csv_path)
        except Exception as exc:
            flash(f"Could not create Excel file: {exc}", "error")
            return redirect(url_for("results"))

        return send_file(
            xlsx_path,
            as_attachment=True,
            download_name=xlsx_path.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/logs")
    def logs():
        config_path = _config_path()
        try:
            config = load_config(config_path)
            log_path = config_path.parent / config.settings.log_file
        except Exception:
            log_path = config_path.parent / "logs/bot.log"

        tail = ""
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-200:])

        return render_template("logs.html", log_content=tail)

    return app
