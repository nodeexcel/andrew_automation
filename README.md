# Trustpilot Automation Bot

Automates natural-looking Trustpilot page visits, search navigation, and suggested-business clicks. Designed to run continuously over a 24-hour period with proxy rotation, device emulation, and multithreaded workers.

## What It Does

| Job Type | Description |
|----------|-------------|
| **direct_visit** | Visit a source Trustpilot review page, scroll, and dwell for a random duration |
| **search_navigate** | Visit a source page → type a keyword in Trustpilot search → click the target result → view target page |
| **suggested_click** | Visit a source page → click the target if it appears in the "Suggested/Recommended" section |
| **target_direct** | Visit the target Trustpilot review page directly |

### Client Use Case

Visit `https://de.trustpilot.com/review/cryptocasinodeutschland.de`, then search for `xsbets.com` and land on `https://de.trustpilot.com/review/xsbets.com`. Once the target appears in suggested terms on the source page, the bot can also click it there.

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

- **`source_urls`** — list of Trustpilot pages to start from
- **`target_url`** — the page you want to reach
- **`target_keywords`** — search terms to type in Trustpilot search
- **`jobs`** — how many of each job type to run over 24 hours

### 3. Add proxies (optional but recommended)

Edit `proxies.txt` — one proxy per line:

```
http://user:pass@proxy1.example.com:8080
http://user:pass@proxy2.example.com:8080
```

### 4. Preview planned jobs

```bash
python main.py --dry-run
```

### 5. Quick test (runs all 4 job types once, browser visible)

```bash
python main.py --test
```

### 6. Run for 24 hours

```bash
python main.py
```

To watch the browser (debugging):

```yaml
# config.yaml
settings:
  headless: false
```

## Configuration Reference

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `run_duration_hours` | 24 | How long the bot runs |
| `min_page_duration` | 25 | Min seconds on each page |
| `max_page_duration` | 90 | Max seconds on each page |
| `min_task_interval` | 180 | Min seconds between tasks (per worker) |
| `max_task_interval` | 900 | Max seconds between tasks (per worker) |
| `max_workers` | 3 | Concurrent browser threads |
| `headless` | true | Run browsers invisibly |
| `trustpilot_locale` | de | Trustpilot locale (de, www, uk, etc.) |

### Multiple Campaigns

You can run several source → target pairs at once:

```yaml
campaigns:
  - name: "campaign A"
    enabled: true
    source_urls:
      - "https://de.trustpilot.com/review/source-a.de"
      - "https://de.trustpilot.com/review/source-b.de"
    target_url: "https://de.trustpilot.com/review/target.com"
    target_keywords:
      - "target"
      - "target.com"
    jobs:
      direct_visit: 20
      search_navigate: 30
      suggested_click: 15
      target_direct: 10

  - name: "campaign B"
    enabled: true
    source_urls:
      - "https://de.trustpilot.com/review/another-source.com"
    target_url: "https://de.trustpilot.com/review/another-target.com"
    target_keywords:
      - "another target"
    jobs:
      direct_visit: 10
      search_navigate: 20
      suggested_click: 5
      target_direct: 5
```

### Job Counts (per 24h period)

Set how many times each action runs:

```yaml
jobs:
  direct_visit: 20        # browse source pages
  search_navigate: 30     # search → click target
  suggested_click: 15     # click target in suggested section
  target_direct: 10       # visit target directly
```

## Features

- **Variable URLs** — source and target URLs are fully configurable lists
- **Keyword search** — simulates human typing in Trustpilot search
- **Suggested clicks** — finds and clicks target in recommended sections
- **Proxy support** — rotates through a proxy list per job
- **Device emulation** — random desktop/mobile user-agents, viewports, timezones
- **Human-like behavior** — scrolling, variable dwell times, typing delays
- **Multithreaded** — multiple workers run jobs in parallel
- **24h scheduling** — jobs are randomly distributed across the run period
- **Variable intervals** — random delays between tasks to spread proxy usage

## Logs

Activity is logged to `logs/bot.log` and printed to the console.

## Project Structure

```
andrew_automation/
├── main.py              # Entry point
├── config.yaml          # Your active config (gitignored)
├── config.example.yaml  # Template
├── proxies.txt          # Proxy list (gitignored)
├── requirements.txt
├── bot/
│   ├── browser.py       # Browser + proxy + device setup
│   ├── config.py        # Config loader
│   ├── devices.py       # User-agent / viewport profiles
│   ├── jobs.py          # Job types and execution
│   ├── logger.py        # Logging
│   ├── scheduler.py     # 24h multithreaded scheduler
│   └── trustpilot.py    # Trustpilot page interactions
└── logs/
```

## Running in Production

Use a process manager to keep the bot alive across restarts:

```bash
# systemd, screen, tmux, or cron to restart daily:
nohup python main.py >> logs/output.log 2>&1 &
```

## Custom Config Path

```bash
python main.py --config /path/to/my-config.yaml
# or
BOT_CONFIG=/path/to/my-config.yaml python main.py
```
