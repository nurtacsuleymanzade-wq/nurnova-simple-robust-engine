"""Run S14 — Flow Persistence Engine."""

from src.simple.flow_persistence_engine import run_flow_persistence_engine

if __name__ == "__main__":
    result = run_flow_persistence_engine()
    print(f"persistence_label    : {result['persistence_label']}")
    print(f"direction_label      : {result['direction_label']}")
    print(f"persistence_score    : {result['persistence_score']}")
    print(f"continuation_quality : {result['continuation_quality']}")
    print(f"decay_risk           : {result['decay_risk']}")
    print(f"flip_risk            : {result['flip_risk']}")
    print(f"input_status         : {result['input_status']}")
    print(f"safe_to_trade        : {result['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next           : {result['feeds_next']['next_blocks']}")
