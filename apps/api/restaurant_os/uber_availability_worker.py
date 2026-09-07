"""Bounded worker for durable Uber Eats availability commands."""

from __future__ import annotations

import argparse
import signal
from threading import Event

from .database import get_session_factory
from .integrations.service import channel_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch durable Uber Eats availability commands")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.batch_size < 1 or args.poll_seconds <= 0:
        parser.error("--batch-size and --poll-seconds must be positive")
    stopping = Event()

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    sessions = get_session_factory()
    while not stopping.is_set():
        channel_service.dispatch_due_uber_availability_syncs(sessions, args.batch_size)
        if args.once:
            return 0
        stopping.wait(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
