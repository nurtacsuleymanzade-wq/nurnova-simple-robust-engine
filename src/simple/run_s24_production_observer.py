"""Run S24 — Production Observer. 24/7 VPS systemd-ready cycle loop.

Paper-only. No private API. No real orders. safe_to_open_real_trade always False.

Usage:
    python -m src.simple.run_s24_production_observer
    python -m src.simple.run_s24_production_observer --interval-seconds 60 --dry-run-alerts
    python -m src.simple.run_s24_production_observer --cycles 2 --interval-seconds 1
"""

from __future__ import annotations

import argparse

from src.simple.production_observer import run_observer_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="S24 Production Observer (paper-only 24/7 loop)")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Seconds between cycles (default: 60)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Max cycles to run (omit for infinite loop)",
    )
    parser.add_argument(
        "--dry-run-alerts",
        action="store_true",
        default=True,
        help="Use DRY_RUN for Telegram alerts (default: True)",
    )
    parser.add_argument(
        "--send-paper-alerts",
        action="store_true",
        default=False,
        help="Send real Telegram paper alerts (requires env vars; still paper-only)",
    )
    args = parser.parse_args()

    dry_run = not args.send_paper_alerts

    run_observer_loop(
        interval_seconds=args.interval_seconds,
        dry_run_alerts=dry_run,
        max_cycles=args.cycles,
    )


if __name__ == "__main__":
    main()
