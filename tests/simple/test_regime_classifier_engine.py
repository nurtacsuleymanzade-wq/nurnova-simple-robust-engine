from __future__ import annotations

import json
from pathlib import Path

import src.simple.regime_classifier_engine as m


def _required_fields() -> set[str]:
    return {
        "timestamp_utc",
        "block_id",
        "symbol",
        "data_quality",
        "regime_status",
        "primary_regime",
        "directional_bias",
        "volatility_state",
        "trend_strength",
        "range_strength",
        "compression_score",
        "expansion_score",
        "reversal_risk",
        "allowed_setup_families",
        "blocked_setup_families",
        "confidence",
        "reason_codes",
        "source",
        "feeds_next",
    }


def test_output_created_and_required_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_regime_classifier.json")
    monkeypatch.setattr(m, "MARKET_STRUCTURE_V2_PATH", tmp_path / "latest_market_structure_v2.json")
    sample = m._fake_trend_up_structure("BTCUSDT")
    (tmp_path / "latest_market_structure_v2.json").write_text(json.dumps(sample), encoding="utf-8")
    result = m.run_regime_classifier_engine(symbol="BTCUSDT", fake_sample=False)
    assert m.OUTPUT_PATH.exists()
    disk = json.loads(m.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert _required_fields().issubset(set(result.keys()))
    assert _required_fields().issubset(set(disk.keys()))


def test_not_ready_when_structure_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_regime_classifier.json")
    monkeypatch.setattr(m, "MARKET_STRUCTURE_V2_PATH", tmp_path / "missing_structure.json")
    result = m.run_regime_classifier_engine(symbol="BTCUSDT", fake_sample=False)
    assert result["regime_status"] == "NOT_READY"
    assert result["primary_regime"] == "UNKNOWN"


def test_fake_trend_up_generates_trend_long(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_regime_classifier.json")
    result = m.run_regime_classifier_engine(symbol="BTCUSDT", fake_sample=True)
    assert result["primary_regime"] == "TREND"
    assert result["directional_bias"] == "LONG"


def test_fake_range_generates_range_neutral() -> None:
    structure = {
        "structure_status": "READY",
        "regime_hint": "RANGE",
        "trend_direction": "NEUTRAL",
        "structure_bias": "NEUTRAL",
        "confidence": 0.7,
        "bos": None,
        "choch": None,
    }
    result = m.build_regime_classifier(symbol="BTCUSDT", structure_payload=structure)
    assert result["primary_regime"] == "RANGE"
    assert result["directional_bias"] == "NEUTRAL"


def test_allowed_setup_families_list_generated() -> None:
    structure = {
        "structure_status": "READY",
        "regime_hint": "TREND_UP",
        "trend_direction": "LONG",
        "structure_bias": "LONG",
        "confidence": 0.8,
        "bos": "BULLISH_BOS",
        "choch": None,
    }
    result = m.build_regime_classifier(symbol="BTCUSDT", structure_payload=structure)
    assert isinstance(result["allowed_setup_families"], list)
    assert "TREND_CONTINUATION_LONG" in result["allowed_setup_families"]
