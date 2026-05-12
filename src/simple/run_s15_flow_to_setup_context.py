"""Run S15 — Flow-to-Setup Context Engine."""

from src.simple.flow_to_setup_context_engine import run_flow_to_setup_context_engine

if __name__ == "__main__":
    result = run_flow_to_setup_context_engine()
    print(f"setup_context_label  : {result['setup_context_label']}")
    print(f"setup_context_score  : {result['setup_context_score']}")
    print(f"direction_bias       : {result['direction_bias']}")
    print(f"long_probability     : {result['long_probability']}")
    print(f"short_probability    : {result['short_probability']}")
    print(f"confidence           : {result['confidence']}")
    print(f"tradeable            : {result['tradeable']}")
    print(f"input_status         : {result['input_status']}")
    print(f"safe_to_trade        : {result['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next           : {result['feeds_next']['next_blocks']}")
