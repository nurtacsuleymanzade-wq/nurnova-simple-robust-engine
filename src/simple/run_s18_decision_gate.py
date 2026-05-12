"""Run S18 — Decision Gate Engine."""

from src.simple.decision_gate_engine import run_decision_gate_engine

if __name__ == "__main__":
    r = run_decision_gate_engine()
    print(f"decision              : {r['decision']}")
    print(f"decision_status       : {r['decision_status']}")
    print(f"final_grade           : {r['final_grade']}")
    print(f"decision_score        : {r['decision_score']}")
    print(f"allowed_paper_alert   : {r['allowed_for_paper_alert']}")
    print(f"allowed_lifecycle     : {r['allowed_for_paper_lifecycle']}")
    print(f"selected_side         : {r['selected_side']}")
    print(f"selected_entry        : {r['selected_entry']}")
    print(f"selected_stop_loss    : {r['selected_stop_loss']}")
    print(f"selected_tp1          : {r['selected_tp1']}")
    print(f"selected_tp2          : {r['selected_tp2']}")
    print(f"block_reasons         : {r['block_reasons']}")
    print(f"warning_reasons       : {r['warning_reasons']}")
    print(f"safe_to_trade         : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next            : {r['feeds_next']['next_blocks']}")
