from __future__ import annotations

import json
from pathlib import Path

import src.simple.contract_edge_matrix_engine as m


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for r in rows:
            handle.write(json.dumps(r) + "\n")


def _closed(contract_id: str | None, r: float, regime: str = "TREND") -> dict:
    return {
        "trades_closed_this_loop": [
            {
                "contract_id": contract_id,
                "setup_family": "TREND_CONTINUATION_LONG",
                "direction": "LONG",
                "primary_regime": regime,
                "structure_bias": "LONG",
                "liquidity_bias": "BALANCED",
                "rr1": 1.2,
                "rr2": 1.8,
                "close_reason": "TP1_HIT" if r > 0 else "SL_HIT",
                "outcome_status": "CLOSED",
                "r_result": r,
                "opened_at_utc": "2026-05-16T00:00:00Z",
                "closed_at_utc": "2026-05-16T00:10:00Z",
            }
        ]
    }


def test_empty_history_no_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "PAPER_LIFECYCLE_HISTORY_PATH", tmp_path / "paper_lifecycle_history.jsonl")
    monkeypatch.setattr(m, "RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH", tmp_path / "research_paper_lifecycle_history.jsonl")
    monkeypatch.setattr(m, "TRUE_OUTCOME_HISTORY_PATH", tmp_path / "true_outcome_history.jsonl")
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=False)
    assert out["sample_summary"]["closed_count"] == 0


def test_fake_closed_trades_compute_metrics_and_grouping(tmp_path: Path, monkeypatch) -> None:
    p1 = tmp_path / "paper_lifecycle_history.jsonl"
    p2 = tmp_path / "research_paper_lifecycle_history.jsonl"
    p3 = tmp_path / "true_outcome_history.jsonl"
    _write_jsonl(p1, [_closed("SC003", 1.5), _closed("SC003", -1.0), _closed("SC004", 0.8)])
    _write_jsonl(p2, [])
    _write_jsonl(p3, [])
    monkeypatch.setattr(m, "PAPER_LIFECYCLE_HISTORY_PATH", p1)
    monkeypatch.setattr(m, "RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH", p2)
    monkeypatch.setattr(m, "TRUE_OUTCOME_HISTORY_PATH", p3)
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=False)
    assert out["sample_summary"]["closed_count"] == 3
    assert len(out["by_contract"]) >= 2
    assert out["sample_summary"]["winrate"] >= 0.0
    assert "SC003" in {x["contract_id"] for x in out["by_contract"]}


def test_sample_size_5_early_signal(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "paper_lifecycle_history.jsonl"
    _write_jsonl(p, [_closed("SC003", 1.0) for _ in range(5)])
    monkeypatch.setattr(m, "PAPER_LIFECYCLE_HISTORY_PATH", p)
    monkeypatch.setattr(m, "RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH", tmp_path / "r.jsonl")
    monkeypatch.setattr(m, "TRUE_OUTCOME_HISTORY_PATH", tmp_path / "t.jsonl")
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=False)
    signals = [x for x in out["early_signals"] if x["contract_id"] == "SC003"]
    assert signals and signals[0]["sample_size"] >= 5


def test_sample_size_20_positive_expectancy_tradeable(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "paper_lifecycle_history.jsonl"
    _write_jsonl(p, [_closed("SC003", 1.1) for _ in range(20)])
    monkeypatch.setattr(m, "PAPER_LIFECYCLE_HISTORY_PATH", p)
    monkeypatch.setattr(m, "RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH", tmp_path / "r.jsonl")
    monkeypatch.setattr(m, "TRUE_OUTCOME_HISTORY_PATH", tmp_path / "t.jsonl")
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=False)
    assert any(x["contract_id"] == "SC003" for x in out["tradeable_candidates"])


def test_legacy_samples_are_separated(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "paper_lifecycle_history.jsonl"
    _write_jsonl(p, [_closed(None, -1.0), _closed("SC003", 1.0)])
    monkeypatch.setattr(m, "PAPER_LIFECYCLE_HISTORY_PATH", p)
    monkeypatch.setattr(m, "RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH", tmp_path / "r.jsonl")
    monkeypatch.setattr(m, "TRUE_OUTCOME_HISTORY_PATH", tmp_path / "t.jsonl")
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=False)
    assert out["sample_summary"]["legacy_sample_count"] == 1
    assert "LEGACY_SAMPLE_NO_CONTRACT_ID" in out["reason_codes"]


def test_report_file_created(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_edge_matrix.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(m, "REPORT_PATH", tmp_path / "contract_edge_matrix_latest_report.md")
    out = m.run_contract_edge_matrix_engine(symbol="BTCUSDT", fake_sample=True)
    assert out["block_id"] == "CONTRACT_EDGE_MATRIX"
    assert m.REPORT_PATH.exists()

