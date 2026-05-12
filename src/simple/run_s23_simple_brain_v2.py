"""Run S23 — Simple Brain v2 (read-only aggregation, no real orders)."""

from __future__ import annotations

from src.simple.simple_brain_v2 import run_simple_brain_v2


def main() -> None:
    r = run_simple_brain_v2()
    print(f"symbol             : {r['symbol']}")
    print(f"input_status       : {r['input_status']}")
    print(f"brain_status       : {r['brain_status']}")
    print(f"brain_mode         : {r['brain_mode']}")
    print(f"primary_reading    : {r['primary_reading']}")
    print(f"primary_risk       : {r['primary_risk']}")
    print(f"primary_next_action: {r['primary_next_action']}")
    print(f"data_quality       : {r['data_quality']['level']}")
    print(f"safe_to_open_real  : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next         : {r['feeds_next']['next_blocks']}")


if __name__ == "__main__":
    main()
