"""Integration delivery worker: python -m app.worker
Health check: python -m app.worker --check (exit 0 if the heartbeat was updated within 60 s; used by the container health check)

Uses the same image as the backend and runs as a separate worker service. Several can run; jobs are claimed with row locks + READPAST, so nothing is delivered twice.
"""

import logging
import signal
import socket
import sys
import time
from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.observability import configure_logging
from app.models.integration import WorkerHeartbeat
from app.services import integration_service as svc
from app.services.document_common import utcnow

log = logging.getLogger("wms.worker")
PURGE_EVERY_SECONDS = 3600

_stopping = False


def _stop(*_):
    global _stopping
    _stopping = True
    log.info("Stop signal received; exiting after the current job")


def run_once() -> int:
    """One round: dispatch new events and deliver due jobs. Returns the number handled this round (also used by tests)."""
    handled = 0
    with SessionLocal() as db:
        handled += svc.dispatch_events(db)
        for job_id in svc.claim_jobs(db):
            ok = svc.deliver(db, job_id)
            log.info("Delivery %s %s", job_id, "succeeded" if ok else "failed")
            handled += 1
    return handled


def check() -> int:
    with SessionLocal() as db:
        row = db.get(WorkerHeartbeat, svc.WORKER_NAME)
        alive = row is not None and row.last_seen > utcnow() - timedelta(seconds=60)
    print("ok" if alive else "no recent heartbeat")
    return 0 if alive else 1


def main() -> None:
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    info = f"{socket.gethostname()} v{settings.app_version}"
    log.info("Integration worker started (%s, polling every %s s)", info, settings.integration_poll_seconds)
    last_purge = 0.0
    while not _stopping:
        try:
            with SessionLocal() as db:
                svc.heartbeat(db, info)
            busy = run_once()
            if time.monotonic() - last_purge > PURGE_EVERY_SECONDS:
                with SessionLocal() as db:
                    removed = svc.purge(db, settings.integration_retention_days)
                if removed:
                    log.info("Purged %s expired delivery records", removed)
                last_purge = time.monotonic()
        except Exception:  # noqa: BLE001 - e.g. database briefly unavailable; log and retry next round
            log.exception("Error in this round")
            busy = 0
        if not busy:
            time.sleep(settings.integration_poll_seconds)


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    main()
