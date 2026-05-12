"""Run S19 — Telegram Paper Alert Engine."""

from __future__ import annotations

import argparse

from src.simple.telegram_paper_alert_engine import run_telegram_paper_alert_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="S19 Telegram Paper Alert (paper only)")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="DRY_RUN mode (default)")
    g.add_argument("--send", action="store_true", help="SEND mode (requires env vars)")
    args = parser.parse_args()

    mode = "SEND" if args.send else "DRY_RUN"
    r = run_telegram_paper_alert_engine(mode=mode)

    print(f"alert_status   : {r['alert_status']}")
    print(f"telegram_mode  : {r['telegram_mode']}")
    print(f"dry_run        : {r['dry_run']}")
    print(f"sent           : {r['sent']}")
    print(f"decision       : {r['decision']}")
    print(f"symbol         : {r['symbol']}")
    print(f"side           : {r['side']}")
    print(f"entry_price    : {r['entry_price']}")
    print(f"stop_loss      : {r['stop_loss']}")
    print(f"tp1            : {r['tp1']}")
    print(f"tp2            : {r['tp2']}")
    print(f"final_grade    : {r['final_grade']}")
    print(f"safe_to_trade  : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next     : {r['feeds_next']['next_blocks']}")


if __name__ == "__main__":
    main()
