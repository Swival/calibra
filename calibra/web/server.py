"""Uvicorn launcher for calibra web serve."""

from __future__ import annotations

import webbrowser
from pathlib import Path


def run_server(
    results_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8118,
    open_browser: bool = False,
) -> None:
    import uvicorn

    from calibra.web import create_app

    app = create_app(results_dir)

    if open_browser:
        import threading

        def _open():
            import time

            time.sleep(0.5)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
