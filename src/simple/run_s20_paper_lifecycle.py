"""Run S20 — Paper Lifecycle Tracker (paper only)."""

from __future__ import annotations

from src.simple.paper_lifecycle_tracker import run_paper_lifecycle_tracker


def main() -> None:
    r = run_paper_lifecycle_tracker()
    print(f"lifecycle_id     : {r['lifecycle_id']}")
    print(f"lifecycle_status : {r['lifecycle_status']}")
    print(f"symbol           : {r['symbol']}")
    print(f"side             : {r['side']}")
    print(f"entry_price      : {r['entry_price']}")
    print(f"stop_loss        : {r['stop_loss']}")
    print(f"tp1              : {r['tp1']}")
    print(f"tp2              : {r['tp2']}")
    print(f"current_price    : {r['current_price']}")
    print(f"entry_touched    : {r['entry_touched']}")
    print(f"tp1_hit          : {r['tp1_hit']}")
    print(f"tp2_hit          : {r['tp2_hit']}")
    print(f"stop_hit         : {r['stop_hit']}")
    print(f"invalidated      : {r['invalidated']}")
    print(f"unrealized_r     : {r['unrealized_r']}")
    print(f"realized_r       : {r['realized_r']}")
    print(f"MFE_r            : {r['max_favorable_excursion_r']}")
    print(f"MAE_r            : {r['max_adverse_excursion_r']}")
    print(f"safe_to_trade    : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next       : {r['feeds_next']['next_blocks']}")


if __name__ == "__main__":
    main()
