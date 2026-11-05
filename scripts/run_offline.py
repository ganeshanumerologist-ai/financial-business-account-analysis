"""Start ARTHIVIO for a single offline Windows user.

This launcher is used by the portable package. It keeps the database, backups
and logs inside the application folder, opens the browser, and refuses to start
a second copy when ARTHIVIO is already answering on the chosen port.
"""
from __future__ import annotations

import argparse
import os
import socket
import threading
import urllib.error
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as r:
            body = r.read(8).decode("utf-8", "replace").strip()
            server = (r.headers.get("Server") or "").strip()
            return r.status == 200 and body == "ok" and server.startswith("ARTHIVIO/")
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _choose_port(preferred: int) -> tuple[int, bool]:
    """Return (port, already_running)."""
    if _health(preferred):
        return preferred, True
    if _port_free(preferred):
        return preferred, False
    for port in range(preferred + 1, preferred + 20):
        if _health(port):
            return port, True
        if _port_free(port):
            return port, False
    raise RuntimeError("No free local port found in the 8000-8019 range.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the offline ARTHIVIO server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true",
                        help="Start the server without opening a browser window")
    args = parser.parse_args()

    os.chdir(ROOT)
    for folder in ("data", "backups", "logs"):
        os.makedirs(os.path.join(ROOT, folder), exist_ok=True)
    os.environ.setdefault("ARTHIVIO_DB", os.path.join(ROOT, "data", "arthivio.db"))
    os.environ.setdefault("ARTHIVIO_BACKUP_DIR", os.path.join(ROOT, "backups"))
    os.environ.setdefault("ARTHIVIO_LOG_DIR", os.path.join(ROOT, "logs"))
    os.environ.setdefault("ARTHIVIO_HOST", "127.0.0.1")

    port, already_running = _choose_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    if already_running:
        print(f"ARTHIVIO is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    # Import after the environment is set: server and diagnostics read paths at
    # import time.
    from app import server

    print(f"ARTHIVIO offline edition")
    print(f"Open: {url}")
    print(f"Data: {os.environ['ARTHIVIO_DB']}")
    print(f"Backups: {os.environ['ARTHIVIO_BACKUP_DIR']}")
    print(f"Logs: {os.environ['ARTHIVIO_LOG_DIR']}")
    print("Close this window to stop the server. Committed entries survive a power cut.")
    try:
        server.main(port)
    except OSError as exc:
        print(f"Could not start the server: {exc}")
        print("Close any other ARTHIVIO window and try again.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
