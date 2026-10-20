"""Command line: python -m linkedin_relay <befehl>"""

from __future__ import annotations

import argparse
import logging
import threading
import time

from .config import get_settings
from .db import Database
from .pipeline import Pipeline

log = logging.getLogger("linkedin_relay")


def worker_loop(settings, stop: threading.Event | None = None) -> None:
    """Publish due posts every minute; fetch and translate every FETCH_INTERVAL_MINUTES."""
    db = Database(settings.db_path)
    pipeline = Pipeline(settings, db)
    last_fetch = 0.0
    log.info("Worker läuft: Abruf alle %d Minuten, Veröffentlichung minütlich", settings.fetch_interval_minutes)
    while not (stop and stop.is_set()):
        if time.monotonic() - last_fetch >= settings.fetch_interval_minutes * 60 or not last_fetch:
            last_fetch = time.monotonic()
            try:
                pipeline.daily()
            except Exception:
                log.exception("Abruf fehlgeschlagen")
        try:
            pipeline.publish_due()
        except Exception:
            log.exception("Veröffentlichung fehlgeschlagen")
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(prog="linkedin_relay")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("abrufen", help="Eingangsordner und RSS lesen, neue Beiträge übersetzen")
    sub.add_parser("veroeffentlichen", help="Fällige geplante Beiträge posten")
    sub.add_parser("worker", help="Dauerbetrieb ohne Weboberfläche")
    start = sub.add_parser("start", help="Weboberfläche und Worker starten")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=5000)
    start.add_argument("--ohne-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()

    if args.cmd == "abrufen":
        Pipeline(settings, Database(settings.db_path)).daily()
    elif args.cmd == "veroeffentlichen":
        n = Pipeline(settings, Database(settings.db_path)).publish_due()
        log.info("%d Beitrag/Beiträge veröffentlicht", n)
    elif args.cmd == "worker":
        worker_loop(settings)
    elif args.cmd == "start":
        from .web import create_app
        threading.Thread(target=worker_loop, args=(settings,), daemon=True).start()
        if not args.ohne_browser:
            import webbrowser
            threading.Timer(2.0, webbrowser.open, args=(f"http://localhost:{args.port}",)).start()
        print(f"\nLinkedIn Relay läuft: http://localhost:{args.port}  (Fenster offen lassen)\n")
        create_app(settings).run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
