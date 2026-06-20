#!/usr/bin/env python3
"""Launch the Trustpilot bot web interface — the only thing clients need to run."""

from web.bootstrap import ensure_setup
from web.app import create_app

ensure_setup()
app = create_app()

if __name__ == "__main__":
    host = "127.0.0.1"
    port = 5000
    print()
    print("  Trustpilot Bot")
    print("  ------------")
    print(f"  Open in your browser:  http://{host}:{port}")
    print()
    print("  Configure everything in the web app — no code editing required.")
    print()
    app.run(host=host, port=port, debug=False)
