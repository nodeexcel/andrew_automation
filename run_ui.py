#!/usr/bin/env python3
"""Launch the Trustpilot bot web interface — the only thing clients need to run."""

import os

from web.bootstrap import ensure_setup
from web.app import create_app

ensure_setup()
app = create_app()

if __name__ == "__main__":
    host = "127.0.0.1"
    # Port 5000 is often taken by macOS AirPlay (returns HTTP 403 in the browser)
    port = int(os.getenv("BOT_UI_PORT", "5050"))
    url = f"http://{host}:{port}"
    print()
    print("  Trustpilot Bot")
    print("  ------------")
    print(f"  Open in your browser:  {url}")
    print()
    print("  Use http (not https). Keep this terminal open while using the app.")
    print()
    app.run(host=host, port=port, debug=False)
