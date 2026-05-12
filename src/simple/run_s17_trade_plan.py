"""Run S17 — Trade Plan Engine."""

from src.simple.trade_plan_engine import run_trade_plan_engine

if __name__ == "__main__":
    r = run_trade_plan_engine()
    print(f"plan_status         : {r['plan_status']}")
    print(f"plan_grade          : {r['plan_grade']}")
    print(f"side                : {r['side']}")
    print(f"entry_price         : {r['entry_price']}")
    print(f"stop_loss           : {r['stop_loss']}")
    print(f"tp1                 : {r['tp1']}")
    print(f"tp2                 : {r['tp2']}")
    print(f"rr_tp1              : {r['rr_tp1']}")
    print(f"rr_tp2              : {r['rr_tp2']}")
    print(f"invalidation_price  : {r['invalidation_price']}")
    print(f"plan_quality_score  : {r['plan_quality_score']}")
    print(f"data_quality        : {r['data_quality']['level']}")
    print(f"safe_to_trade       : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next          : {r['feeds_next']['next_blocks']}")
