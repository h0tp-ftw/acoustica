"""Web-based tuner for creating and testing alarm profiles.

Run with: python -m acoustic_engine.tuner
"""

import http.server
import os
import socketserver
import sys
import webbrowser
from pathlib import Path


def get_tuner_dir() -> Path:
    """Get the directory containing tuner files."""
    return Path(__file__).parent


def main(port: int = 8080, open_browser: bool = True):
    """Start the tuner web server.

    Args:
        port: HTTP port to serve on (default 8080)
        open_browser: Whether to open a browser automatically
    """
    tuner_dir = get_tuner_dir()

    os.chdir(tuner_dir)

    handler = http.server.SimpleHTTPRequestHandler

    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print("🎵 Alarm Audio Tuner")
        print(f"   Serving at: {url}")
        print("   Press Ctrl+C to stop")
        print()

        if open_browser:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Tuner stopped")
            sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Alarm Audio Tuner")
    parser.add_argument(
        "-p", "--port", type=int, default=8080, help="Port to serve on (default: 8080)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser automatically"
    )

    args = parser.parse_args()
    main(port=args.port, open_browser=not args.no_browser)
