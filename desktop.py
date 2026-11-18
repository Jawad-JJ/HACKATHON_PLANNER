"""Laptop app experience: starts the local backend and opens the dashboard in its own window.

    python desktop.py

Uses Edge or Chrome in --app mode (a window without browser chrome); falls back to the default
browser. The same dashboard can also be installed as a PWA from the browser's install button.
"""
import os
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer

from serve import Handler

PORT = int(os.getenv("PORT", "8000"))
URL = f"http://127.0.0.1:{PORT}/"


def app_window(url):
    candidates = [shutil.which(n) for n in ("msedge", "chrome", "google-chrome", "chromium")] + [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    for exe in candidates:
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"])
            return
    webbrowser.open(url)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    app_window(URL)
    print(f"PlanForge running at {URL} - close this window (Ctrl+C) to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
