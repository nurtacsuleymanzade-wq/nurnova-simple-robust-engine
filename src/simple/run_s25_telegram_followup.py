"""Run S25 Telegram follow-up notifier."""

from __future__ import annotations

from src.simple.telegram_followup_notifier import run_telegram_followup_notifier


def main() -> None:
    result = run_telegram_followup_notifier()
    print(f"followup_status : {result['followup_status']}")
    print(f"event_type       : {result['event_type']}")
    print(f"telegram_sent    : {result['telegram_sent']}")
    print(f"safe_to_open_real_trade : {result['safe_to_open_real_trade']}")


if __name__ == "__main__":
    main()
