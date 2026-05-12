"""Run S21 — Outcome Monitor (paper only, no real orders)."""

from __future__ import annotations

from src.simple.outcome_monitor import run_outcome_monitor


def main() -> None:
    r = run_outcome_monitor()
    print(f"lifecycle_id    : {r['lifecycle_id']}")
    print(f"outcome_status  : {r['outcome_status']}")
    print(f"outcome_result  : {r['outcome_result']}")
    print(f"close_reason    : {r['close_reason']}")
    print(f"symbol          : {r['symbol']}")
    print(f"side            : {r['side']}")
    print(f"entry_price     : {r['entry_price']}")
    print(f"stop_loss       : {r['stop_loss']}")
    print(f"tp1             : {r['tp1']}")
    print(f"tp2             : {r['tp2']}")
    print(f"final_price     : {r['final_price']}")
    print(f"realized_r      : {r['realized_r']}")
    print(f"mfe_r           : {r['mfe_r']}")
    print(f"mae_r           : {r['mae_r']}")
    print(f"safe_to_trade   : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next      : {r['feeds_next']['next_blocks']}")


if __name__ == "__main__":
    main()
