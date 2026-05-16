from __future__ import annotations

import json
from pathlib import Path

import src.simple.market_structure_v2_engine as m


def _required_fields() -> set[str]:
    return {
        "timestamp_utc",
        "block_id",
        "symbol",
        "data_quality",
        "structure_status",
        "regime_hint",
        "trend_direction",
        "swing_highs",
        "swing_lows",
        "equal_highs",
        "equal_lows",
        "last_hh",
        "last_hl",
        "last_lh",
        "last_ll",
        "bos",
        "choch",
        "recent_sweep",
        "structure_bias",
        "confidence",
        "reason_codes",
        "feeds_next",
    }


def test_output_file_created_and_required_fields_complete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "latest_market_truth.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "latest_hybrid_candle_dna.json")
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=True)
    assert m.OUTPUT_PATH.exists()
    on_disk = json.loads(m.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert _required_fields().issubset(set(on_disk.keys()))
    assert _required_fields().issubset(set(result.keys()))


def test_not_ready_when_data_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "missing_market_truth.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "missing_hybrid.json")
    monkeypatch.setattr(m, "LATEST_1S_EVIDENCE_PATH", tmp_path / "missing_1s_evidence.json")
    monkeypatch.setattr(m, "ONE_SECOND_EVIDENCE_JSONL_PATH", tmp_path / "missing_one_second_evidence.jsonl")
    monkeypatch.setattr(m, "HYBRID_DNA_JSONL_PATH", tmp_path / "missing_hybrid_dna.jsonl")
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=False)
    assert result["structure_status"] == "NOT_READY"
    assert result["structure_bias"] == "NEUTRAL"
    assert "INSUFFICIENT_CANDLES_FOR_STRUCTURE" in result["reason_codes"]


def test_fake_sample_generates_swings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "latest_market_truth.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "latest_hybrid_candle_dna.json")
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=True)
    assert isinstance(result["swing_highs"], list)
    assert isinstance(result["swing_lows"], list)
    assert len(result["swing_highs"]) > 0 or len(result["swing_lows"]) > 0


def test_feeds_next_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=True)
    assert "feeds_next" in result
    assert isinstance(result["feeds_next"], list)
    assert len(result["feeds_next"]) > 0


def test_structure_bias_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=True)
    assert result["structure_bias"] in {"LONG", "SHORT", "NEUTRAL"}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_1s_evidence_jsonl_can_make_ready_and_swings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "ONE_SECOND_EVIDENCE_JSONL_PATH", tmp_path / "one_second_evidence.jsonl")
    monkeypatch.setattr(m, "HYBRID_DNA_JSONL_PATH", tmp_path / "missing_hybrid_dna.jsonl")
    monkeypatch.setattr(m, "LATEST_1S_EVIDENCE_PATH", tmp_path / "latest_1s_evidence.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "latest_hybrid_candle_dna.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "latest_market_truth.json")

    rows: list[dict] = []
    base = 1778856000
    pattern = [0, 5, 10, 5, 0, -5, -10, -5] * 4
    for minute in range(30):
        for sec in range(10):
            ts = base + minute * 60 + sec
            px = 79000 + pattern[minute] + (0.2 if sec % 2 == 0 else -0.2)
            rows.append({"second_epoch": ts, "open": px, "high": px + 1, "low": px - 1, "close": px})
    _write_jsonl(tmp_path / "one_second_evidence.jsonl", rows)

    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=False)
    assert "CANDLES_FROM_1S_EVIDENCE" in result["reason_codes"]
    assert result["structure_status"] in {"READY", "NOT_READY"}
    assert len(result["swing_highs"]) > 0 or len(result["swing_lows"]) > 0


def test_malformed_jsonl_line_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "ONE_SECOND_EVIDENCE_JSONL_PATH", tmp_path / "one_second_evidence.jsonl")
    monkeypatch.setattr(m, "HYBRID_DNA_JSONL_PATH", tmp_path / "missing_hybrid_dna.jsonl")
    monkeypatch.setattr(m, "LATEST_1S_EVIDENCE_PATH", tmp_path / "latest_1s_evidence.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "latest_hybrid_candle_dna.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "latest_market_truth.json")

    path = tmp_path / "one_second_evidence.jsonl"
    path.write_text(
        '{"second_epoch":1778856742,"open":79035.91,"high":79035.91,"low":79035.9,"close":79035.91}\n'
        'json{"second_epoch":1778856802,"open":79036.00,"high":79036.10,"low":79035.80,"close":79036.00}\n'
        "{bad json line}\n",
        encoding="utf-8",
    )
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=False)
    assert result["block_id"] == "MARKET_STRUCTURE_V2"
    assert m.OUTPUT_PATH.exists()
    assert (
        "CANDLES_FROM_1S_EVIDENCE" in result["reason_codes"]
        or "INSUFFICIENT_CANDLES_FOR_STRUCTURE" in result["reason_codes"]
    )


def test_hybrid_dna_jsonl_is_highest_priority_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_market_structure_v2.json")
    monkeypatch.setattr(m, "HYBRID_DNA_JSONL_PATH", tmp_path / "hybrid_candle_dna.jsonl")
    monkeypatch.setattr(m, "ONE_SECOND_EVIDENCE_JSONL_PATH", tmp_path / "one_second_evidence.jsonl")
    monkeypatch.setattr(m, "LATEST_1S_EVIDENCE_PATH", tmp_path / "latest_1s_evidence.json")
    monkeypatch.setattr(m, "LATEST_HYBRID_DNA_PATH", tmp_path / "latest_hybrid_candle_dna.json")
    monkeypatch.setattr(m, "LATEST_MARKET_TRUTH_PATH", tmp_path / "latest_market_truth.json")

    rows: list[dict] = []
    base = 1778856000
    pattern = [0, 5, 10, 5, 0, -5, -10, -5, 0, 6]
    for idx, p in enumerate(pattern):
        px = 78190 + p
        rows.append(
            {
                "timestamp_utc": f"2026-05-16T00:{idx:02d}:00Z",
                "official_candle": {"open": px - 1, "high": px + 2, "low": px - 2, "close": px},
            }
        )
    _write_jsonl(tmp_path / "hybrid_candle_dna.jsonl", rows)

    # Put competing source too; hybrid jsonl should still win.
    _write_jsonl(
        tmp_path / "one_second_evidence.jsonl",
        [{"second_epoch": base + i, "open": 79000, "high": 79001, "low": 78999, "close": 79000} for i in range(60)],
    )

    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=False)
    assert m.OUTPUT_PATH.exists()
    assert "CANDLES_FROM_HYBRID_DNA_JSONL" in result["reason_codes"]
    assert result["block_id"] == "MARKET_STRUCTURE_V2"
