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
    result = m.run_market_structure_v2_engine(symbol="BTCUSDT", fake_sample=False)
    assert result["structure_status"] == "NOT_READY"
    assert result["structure_bias"] == "NEUTRAL"
    assert "INSUFFICIENT_CANDLES" in result["reason_codes"]


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

