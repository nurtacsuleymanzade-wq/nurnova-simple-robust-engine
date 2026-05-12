"""Run S13 — 1S Flow Evidence Engine."""

from src.simple.flow_evidence_engine import run_flow_evidence_engine

if __name__ == "__main__":
    result = run_flow_evidence_engine()
    print(f"evidence_label  : {result['evidence_label']}")
    print(f"evidence_score  : {result['evidence_score']}")
    print(f"confidence      : {result['confidence']}")
    print(f"pressure_label  : {result['pressure_evidence']['pressure_label']}")
    print(f"input_status    : {result['input_status']}")
    print(f"safe_to_trade   : {result['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next      : {result['feeds_next']['next_blocks']}")
