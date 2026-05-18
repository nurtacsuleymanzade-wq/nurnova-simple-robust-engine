from __future__ import annotations

from typing import Any


NODE_TYPES = (
    "raw_event",
    "evidence",
    "candle_dna",
    "footprint",
    "liquidity",
    "structure",
    "market_state",
    "scenario",
    "setup_candidate",
    "entry_trigger",
    "trade_plan",
    "decision",
    "paper_trade",
    "outcome",
    "edge_row",
    "replay",
    "brain_snapshot",
)


BASE_REQUIRED_FIELDS = [
    "lineage_id",
    "node_type",
    "source_block",
    "timestamp_utc",
    "symbol",
    "parent_lineage_ids",
    "child_lineage_ids",
    "context_id",
    "data_quality",
    "reason_codes",
    "feeds_next",
    "source_file",
    "source_record_id",
    "hash_payload",
]


def _spec(
    node_type: str,
    block_id: str,
    expected_parent_types: list[str],
    expected_child_types: list[str],
    criticality: str,
    feeds_next: list[str],
) -> dict[str, Any]:
    return {
        "node_type": node_type,
        "block_id": block_id,
        "expected_parent_types": expected_parent_types,
        "expected_child_types": expected_child_types,
        "required_fields": list(BASE_REQUIRED_FIELDS),
        "criticality": criticality,
        "feeds_next": feeds_next,
    }


LINEAGE_REGISTRY: dict[str, dict[str, Any]] = {
    "raw_event": _spec("raw_event", "S12_FLOW_COLLECTOR", [], ["evidence"], "HIGH", ["S2_1S_EVIDENCE"]),
    "evidence": _spec("evidence", "S2_1S_EVIDENCE", ["raw_event"], ["candle_dna", "footprint"], "HIGH", ["S3_HYBRID_CANDLE_DNA"]),
    "candle_dna": _spec("candle_dna", "S3_HYBRID_CANDLE_DNA", ["evidence"], ["footprint", "liquidity"], "HIGH", ["MTF_CANDLE_DNA_FACTORY"]),
    "footprint": _spec("footprint", "OBSERVATION_FACTORY", ["evidence", "candle_dna"], ["liquidity"], "MEDIUM", ["LIQUIDITY_MAP_ENGINE"]),
    "liquidity": _spec("liquidity", "LIQUIDITY_MAP_ENGINE", ["footprint", "candle_dna"], ["structure"], "HIGH", ["MARKET_STRUCTURE_ENGINE"]),
    "structure": _spec("structure", "MARKET_STRUCTURE_ENGINE", ["liquidity"], ["market_state"], "HIGH", ["MARKET_REGIME_CLASSIFIER"]),
    "market_state": _spec("market_state", "MARKET_REGIME_CLASSIFIER", ["structure"], ["scenario"], "HIGH", ["SCENARIO_ENTRY_TRIGGER"]),
    "scenario": _spec("scenario", "S16_SCENARIO_ENTRY_TRIGGER", ["market_state"], ["setup_candidate"], "HIGH", ["SETUP_CANDIDATE_ENGINE"]),
    "setup_candidate": _spec("setup_candidate", "S6_SCENARIO_SETUP_CANDIDATE", ["scenario"], ["entry_trigger"], "HIGH", ["SIGNAL_EVENT_CONSOLIDATOR"]),
    "entry_trigger": _spec("entry_trigger", "SIGNAL_EVENT_CONSOLIDATOR", ["setup_candidate"], ["trade_plan"], "HIGH", ["S17_TRADE_PLAN_ENGINE"]),
    "trade_plan": _spec("trade_plan", "S17_TRADE_PLAN_ENGINE", ["entry_trigger"], ["decision"], "HIGH", ["S18_DECISION_GATE"]),
    "decision": _spec("decision", "S18_DECISION_GATE", ["trade_plan"], ["paper_trade"], "HIGH", ["S20_PAPER_LIFECYCLE_TRACKER"]),
    "paper_trade": _spec("paper_trade", "S20_PAPER_LIFECYCLE_TRACKER", ["decision"], ["outcome"], "HIGH", ["S21_OUTCOME_MONITOR"]),
    "outcome": _spec("outcome", "S21_OUTCOME_MONITOR", ["paper_trade"], ["edge_row"], "HIGH", ["S22_EDGE_MATRIX_V2"]),
    "edge_row": _spec("edge_row", "RESEARCH_EDGE_MATRIX_ENGINE", ["outcome"], ["replay", "brain_snapshot"], "HIGH", ["S23_SIMPLE_BRAIN_V2"]),
    "replay": _spec("replay", "TRUE_OUTCOME_ENGINE", ["edge_row", "outcome"], ["brain_snapshot"], "MEDIUM", ["EDGE_QUERY_ENGINE"]),
    "brain_snapshot": _spec("brain_snapshot", "S23_SIMPLE_BRAIN_V2", ["edge_row", "replay", "decision"], [], "MEDIUM", []),
}
