"""Run S26 Explainability / Failure Chain Report."""

from __future__ import annotations

from src.simple.explainability_engine import run_explainability_engine


def main() -> None:
    result = run_explainability_engine()
    print(f"block_id              : {result['block_id']}")
    print(f"final_answer          : {result['final_answer']}")
    print(f"no_signal_reason      : {result['no_signal_reason']}")
    print(f"block_stage           : {result['block_stage']}")
    print(f"recommended_next_fix  : {result['recommended_next_fix']}")
    print(f"confidence_to_next    : {result['confidence_to_next_signal']}")
    print(f"safe_to_open_real_trade: {result['execution_safety']['safe_to_open_real_trade']}")


if __name__ == "__main__":
    main()
