"""Run S22 — Edge Matrix v2 (paper-only learning, no real orders)."""

from __future__ import annotations

from src.simple.edge_matrix_v2 import run_edge_matrix_v2


def main() -> None:
    r = run_edge_matrix_v2()
    ss = r["sample_summary"]
    ov = r["overall_stats"]
    eq = r["edge_quality"]
    print(f"symbol             : {r['symbol']}")
    print(f"input_status       : {r['input_status']}")
    print(f"total_records      : {ss['total_records']}")
    print(f"closed_records     : {ss['closed_records']}")
    print(f"open_records       : {ss['open_records']}")
    print(f"no_lifecycle       : {ss['no_lifecycle_records']}")
    print(f"usable_closed      : {ss['usable_closed_records']}")
    print(f"sample_status      : {ss['sample_status']}")
    print(f"win_rate           : {ov['win_rate']}")
    print(f"avg_realized_r     : {ov['avg_realized_r']}")
    print(f"expectancy_r       : {ov['expectancy_r']}")
    print(f"edge_status        : {eq['edge_status']}")
    print(f"edge_score         : {eq['edge_score']}")
    print(f"confidence_level   : {eq['confidence_level']}")
    print(f"safe_to_open_real  : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next         : {r['feeds_next']['next_blocks']}")


if __name__ == "__main__":
    main()
