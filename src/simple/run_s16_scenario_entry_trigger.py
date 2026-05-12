"""Run S16 — Scenario + Entry Trigger Engine."""

from src.simple.scenario_entry_trigger_engine import run_scenario_entry_trigger_engine

if __name__ == "__main__":
    r = run_scenario_entry_trigger_engine()
    print(f"scenario_label       : {r['scenario_label']}")
    print(f"scenario_score       : {r['scenario_score']}")
    print(f"direction_bias       : {r['direction_bias']}")
    print(f"trigger_state        : {r['trigger_state']}")
    print(f"trigger_strength     : {r['trigger_strength']}")
    print(f"trigger_confidence   : {r['trigger_confidence']}")
    print(f"move_prob            : {r['estimated_move_probability']}")
    print(f"failure_prob         : {r['estimated_failure_probability']}")
    print(f"fakeout_prob         : {r['estimated_fakeout_probability']}")
    print(f"market_regime        : {r['market_regime']}")
    print(f"ready_for_entry      : {r['ready_for_entry']}")
    print(f"safe_to_trade        : {r['execution_safety']['safe_to_open_real_trade']}")
    print(f"feeds_next           : {r['feeds_next']['next_blocks']}")
