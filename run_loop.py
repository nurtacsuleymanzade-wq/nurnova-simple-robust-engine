"""
NurNova — Surekli dongu runner v4.
Her 30 saniyede bir pipeline calistirir ve ozet gosterir.
Durdurmak icin: Ctrl+C
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _fmt_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def _extract_prices(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def _compact_scenario_line(kind: str, scenario: dict) -> str:
    condition = str(scenario.get("condition", ""))
    targets = scenario.get("liquidity_targets") or []
    target_text = _fmt_value(targets[0]) if targets else "?"
    prices = _extract_prices(condition)

    if kind == "bull":
        level = prices[0] if prices else "?"
        return f"{level} reclaim->{target_text}"
    if kind == "bear":
        level = prices[0] if prices else "?"
        return f"{level} breakdown->{target_text}"
    if len(prices) >= 2:
        return f"{prices[0]}-{prices[1]} range"
    return "range unresolved"


def _legacy_state_present() -> bool:
    legacy_files = (
        STATE_DIR / "latest_edge_stats.json",
        STATE_DIR / "latest_decision.json",
        STATE_DIR / "latest_outcome.json",
    )
    return any(path.exists() for path in legacy_files)


def run_once() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "src.simple.run_local_full_pipeline"],
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {"error": result.stderr or result.stdout or "bos cikti"}


def print_summary(data: dict, cycle: int) -> None:
    ts = utc_now()
    print(f"\n{'='*60}")
    print(f"  DONGU #{cycle}  |  {ts}")
    print(f"{'='*60}")

    if "error" in data:
        print(f"  HATA: {data['error'][:300]}")
        return

    es = data.get("execution_summary", {})
    dq = data.get("data_quality", {})

    print(f"  Pipeline : {es.get('pipeline_status', '?')}")
    print(f"  Bloklar  : {es.get('blocks_passed', 0)}/{es.get('blocks_total', 0)} PASSED")
    print(f"  Veri     : {dq.get('level', '?')} (skor={dq.get('score', 0)})")
    if _legacy_state_present():
        print("  Uyari    : LEGACY_STATE_PRESENT_BUT_IGNORED")

    for blk in data.get("block_results", []):
        if blk.get("status") not in ("PASSED",):
            print(f"  [{blk['status']}] {blk['block_id']}")

    # --- Fiyat (market_truth icinden) ---
    mt = _read_json(STATE_DIR / "latest_market_truth.json")
    price = None
    if mt:
        price = (mt.get("market_truth") or {}).get("current_price")
        if price is None:
            price = mt.get("current_price")
    print(f"  Fiyat    : {price or '?'} USDT")

    # --- Observation + MTF DNA ---
    observation = _read_json(STATE_DIR / "latest_observation_factory.json")
    if observation:
        winner = ((observation.get("war_reading") or {}).get("who_won", "?"))
        obs_delta = ((observation.get("aggression") or {}).get("delta", "?"))
        obs_spread = ((observation.get("market_snapshot") or {}).get("spread", "?"))
        volume_flow = observation.get("volume_flow") or {}
        print(f"  OBS      : winner={winner} | delta={obs_delta} | spread={obs_spread}")
        print(
            "  VOL      : "
            f"buy={_fmt_value(volume_flow.get('buy_volume'))} "
            f"sell={_fmt_value(volume_flow.get('sell_volume'))} "
            f"delta={_fmt_value(volume_flow.get('delta'))} "
            f"cum_delta={_fmt_value(volume_flow.get('cumulative_delta'))} "
            f"imbalance={_fmt_value(volume_flow.get('volume_imbalance'))}"
        )

    mtf_dna = _read_json(STATE_DIR / "latest_mtf_candle_dna.json")
    if mtf_dna:
        tf_1s = (((mtf_dna.get("1s") or {}).get("war_summary") or {}).get("candle_truth", "UNKNOWN"))
        tf_1m = (((mtf_dna.get("1m") or {}).get("war_summary") or {}).get("candle_truth", "UNKNOWN"))
        tf_5m = (((mtf_dna.get("5m") or {}).get("war_summary") or {}).get("candle_truth", "UNKNOWN"))
        summary = mtf_dna.get("summary") or {}
        produced = summary.get("produced_standard_timeframes", 0)
        total = summary.get("total_standard_timeframes", 12)
        mtf_quality = (mtf_dna.get("data_quality") or {}).get("level", "?")
        print(f"  DNA      : 1s={tf_1s} | 1m={tf_1m} | 5m={tf_5m}")
        print(f"  MTF      : produced={produced}/{total} | quality={mtf_quality}")
        cat_1m = (((mtf_dna.get("1m") or {}).get("candle_category") or {}).get("primary", "UNKNOWN"))
        cat_5m = (((mtf_dna.get("5m") or {}).get("candle_category") or {}).get("primary", "UNKNOWN"))
        cat_15m = (((mtf_dna.get("15m") or {}).get("candle_category") or {}).get("primary", "UNKNOWN"))
        print(f"  CAT      : 1m={cat_1m} | 5m={cat_5m} | 15m={cat_15m}")

    atr_state = _read_json(STATE_DIR / "latest_atr_state.json")
    if atr_state:
        atr_1m = atr_state.get("1m") or {}
        atr_5m = atr_state.get("5m") or {}
        atr_15m = atr_state.get("15m") or {}
        print(
            "  ATR      : "
            f"1m={_fmt_value(atr_1m.get('atr_14'))} "
            f"5m={_fmt_value(atr_5m.get('atr_14'))} "
            f"15m={_fmt_value(atr_15m.get('atr_14'))} "
            f"quality={atr_1m.get('atr_quality', '?')}/{atr_5m.get('atr_quality', '?')}/{atr_15m.get('atr_quality', '?')}"
        )

    market_structure = _read_json(STATE_DIR / "latest_market_structure.json")
    if market_structure:
        str_1m = ((market_structure.get("1m") or {}).get("structure_label", "UNKNOWN"))
        str_5m = ((market_structure.get("5m") or {}).get("structure_label", "UNKNOWN"))
        str_15m = ((market_structure.get("15m") or {}).get("structure_label", "UNKNOWN"))
        str_1h = ((market_structure.get("1h") or {}).get("structure_label", "UNKNOWN"))
        print(f"  STR      : 1m={str_1m} | 5m={str_5m} | 15m={str_15m} | 1h={str_1h}")

    liquidity_map = _read_json(STATE_DIR / "latest_liquidity_map.json")
    if liquidity_map:
        near_levels = liquidity_map.get("near_liquidity") or []
        mid_levels = liquidity_map.get("mid_liquidity") or []
        far_levels = liquidity_map.get("far_liquidity") or []
        top_parts: list[str] = []
        for level in (liquidity_map.get("detected_levels") or [])[:2]:
            ltype = level.get("liquidity_type", "unknown")
            price_text = level.get("price", "?")
            top_parts.append(f"{ltype}@{price_text}")
        top_summary = " / ".join(top_parts) if top_parts else "none"
        print(f"  LIQ      : near={len(near_levels)} mid={len(mid_levels)} far={len(far_levels)} | top={top_summary}")

    interpretation = _read_json(STATE_DIR / "latest_interpretation.json")
    if interpretation:
        int_1m = interpretation.get("1m") or {}
        int_label = int_1m.get("candle_label", "UNKNOWN")
        int_structure = ((int_1m.get("raw_context") or {}).get("structure", "UNKNOWN"))
        int_note = ((int_1m.get("raw_context") or {}).get("cvd_state", "UNKNOWN"))
        print(f"  INT      : 1m={int_label} | structure={int_structure} | note={int_note}")

    scenarios = _read_json(STATE_DIR / "latest_three_scenarios.json")
    if scenarios:
        bull_text = _compact_scenario_line("bull", scenarios.get("bullish_scenario") or {})
        bear_text = _compact_scenario_line("bear", scenarios.get("bearish_scenario") or {})
        neutral_text = _compact_scenario_line("neutral", scenarios.get("neutral_range_scenario") or {})
        print(f"  SCN      : bull={bull_text} | bear={bear_text} | neutral={neutral_text}")

    business_zone = _read_json(STATE_DIR / "latest_business_zone.json")
    if business_zone:
        value_area = business_zone.get("value_area") or {}
        auction = business_zone.get("auction_summary") or {}
        print(
            f"  BIZ      : value={value_area.get('value_position', 'UNKNOWN')} "
            f"| poc={_fmt_value(value_area.get('poc'))} "
            f"| auction={auction.get('auction_state', 'UNKNOWN')}"
        )

    market_regime = _read_json(STATE_DIR / "latest_market_regime.json")
    if market_regime:
        print(
            f"  REG      : mode={market_regime.get('regime', 'UNKNOWN')} "
            f"| day={market_regime.get('day_type', 'UNKNOWN')} "
            f"| bias={market_regime.get('directional_bias', 'UNKNOWN')}"
        )

    intent_analysis = _read_json(STATE_DIR / "latest_intent_analysis.json")
    if intent_analysis:
        intent = intent_analysis.get("intent_analysis") or {}
        print(
            f"  INTENT   : iceberg={intent.get('iceberg_detected', False)} "
            f"spoof={intent.get('spoof_detected', False)} "
            f"trapped={intent.get('trapped_side', 'UNKNOWN')} "
            f"intent={intent.get('intent', 'UNKNOWN')}"
        )

    positioning = _read_json(STATE_DIR / "latest_positioning_context.json")
    if positioning:
        pos = positioning.get("positioning") or {}
        print(
            f"  POS      : crowded={pos.get('crowded_side', 'UNKNOWN')} "
            f"funding={pos.get('funding_context', 'MISSING')} "
            f"oi={pos.get('oi_context', 'MISSING')} "
            f"squeeze={pos.get('squeeze_risk', 'UNKNOWN')}"
        )

    momentum = _read_json(STATE_DIR / "latest_momentum_continuation.json")
    double_dist = _read_json(STATE_DIR / "latest_double_distribution_reversal.json")
    trap = _read_json(STATE_DIR / "latest_trap_trader.json")
    if momentum or double_dist or trap:
        print(
            f"  SETUP_FAM: momentum={bool((momentum or {}).get('active', False))} "
            f"trap={bool((trap or {}).get('active', False))} "
            f"double_dist={bool((double_dist or {}).get('active', False))}"
        )

    unified_context = _read_json(STATE_DIR / "latest_unified_context.json")
    if unified_context:
        readiness = unified_context.get("readiness") or {}
        missing = readiness.get("missing_before_setup") or []
        missing_text = ",".join(missing[:3]) if missing else "none"
        print(
            f"  CTX      : dominant={unified_context.get('dominant_context', 'UNKNOWN')} "
            f"| ready={readiness.get('context_ready_for_setup_selection', False)} "
            f"| missing={missing_text}"
        )

    model_hunter = _read_json(STATE_DIR / "latest_model_hunter.json")
    semantic_validation = _read_json(STATE_DIR / "latest_model_semantic_validation.json")
    model_clusters = _read_json(STATE_DIR / "latest_model_clusters.json")
    model_cooldown = _read_json(STATE_DIR / "latest_model_cooldown.json")
    setup_activation = _read_json(STATE_DIR / "latest_setup_family_activation.json")
    if semantic_validation:
        summary = semantic_validation.get("summary") or {}
        print(
            f"  SEMANTIC : {semantic_validation.get('semantic_health', 'UNKNOWN')} "
            f"errors={summary.get('semantic_error_count', 0)} "
            f"contradictions={summary.get('contradiction_count', 0)}"
        )
    if model_hunter or semantic_validation:
        hunter_summary = model_hunter.get("summary") or {}
        semantic_summary = semantic_validation.get("summary") or {}
        print(
            f"  MODELS   : raw={hunter_summary.get('detected_count', 0)} "
            f"valid={semantic_summary.get('validated_count', 0)} "
            f"blocked_semantic={semantic_summary.get('blocked_count', 0)} "
            f"top={hunter_summary.get('top_model_id', 'UNKNOWN')}"
        )
    if model_clusters or model_cooldown:
        cluster_summary = model_clusters.get("summary") or {}
        cooldown_summary = model_cooldown.get("summary") or {}
        print(
            f"  CLUST     : clusters={cluster_summary.get('cluster_count', 0)} "
            f"allowed={cooldown_summary.get('allowed_count', cluster_summary.get('cluster_count', 0))} "
            f"cooldown_blocked={cooldown_summary.get('blocked_count', 0)}"
        )
    if setup_activation:
        missing = setup_activation.get("missing") or []
        missing_text = ",".join(str(item) for item in missing[:3]) if missing else "none"
        print(
            f"  SETUP_ACT : family={setup_activation.get('dominant_setup_family', 'NO_ACTIVE_SETUP_FAMILY')} "
            f"dir={setup_activation.get('direction', 'NEUTRAL')} "
            f"score={_fmt_value(setup_activation.get('activation_score'))} "
            f"ready={setup_activation.get('ready_for_paper_research', False)} "
            f"missing={missing_text}"
        )

    research_lifecycle = _read_json(STATE_DIR / "latest_research_paper_lifecycle.json")
    if research_lifecycle:
        print(
            f"  PAPER     : opened={len(research_lifecycle.get('new_trades_opened') or [])} "
            f"open={research_lifecycle.get('total_open', 0)} "
            f"closed={research_lifecycle.get('total_closed', 0)}"
        )

    research_edge = _read_json(STATE_DIR / "latest_research_edge_matrix.json")
    if research_edge:
        summary = research_edge.get("summary") or {}
        print(
            f"  REDGE    : best={summary.get('best_model_id', 'UNKNOWN')} "
            f"sample={summary.get('best_sample_size', 0)} "
            f"winrate={_fmt_value(summary.get('best_winrate'))} "
            f"expectancy={_fmt_value(summary.get('best_expectancy'))} "
            f"maturity={summary.get('best_maturity', 'UNKNOWN')}"
        )

    # --- Setup candidate ---
    sc = _read_json(STATE_DIR / "latest_setup_candidate.json")
    if sc:
        src_mode  = (sc.get("source") or {}).get("source_mode", "?")
        cand      = sc.get("setup_candidate") or {}
        direction = cand.get("setup_direction", "?")
        grade     = cand.get("setup_grade", "?")
        status    = cand.get("setup_status", "?")
        score     = cand.get("raw_setup_score", "?")
        align     = (sc.get("evidence_alignment") or {}).get("alignment_label", "?")
        risk      = (sc.get("risk") or {}).get("setup_risk_label", "?")
        print(f"  Setup    : {status} | {direction} | Grade={grade} | skor={score} | {align} | risk={risk} | src={src_mode}")
    else:
        print(f"  Setup    : (dosya yok)")

    # --- Setup context probability ---
    sc_ctx = _read_json(STATE_DIR / "latest_setup_context.json")
    if sc_ctx:
        prob = sc_ctx.get("probability_summary") or {}
        long_pct  = prob.get("long_probability_pct", "?")
        short_pct = prob.get("short_probability_pct", "?")
        sig_class = prob.get("signal_class", "?")
        eligible  = prob.get("signal_eligible", False)
        print(f"  Olasilik : LONG={long_pct}% SHORT={short_pct}% | Sinif={sig_class} | Sinyal={'YES' if eligible else 'NO'}")

    # --- Trade Plan ---
    tp = _read_json(STATE_DIR / "latest_trade_plan.json")
    if tp:
        plan      = tp.get("trade_plan") or tp
        t_status  = plan.get("plan_status", plan.get("trade_plan_status", tp.get("decision_status", "?")))
        direction = plan.get("direction", plan.get("side", "?"))
        entry     = plan.get("entry_price", "?")
        sl        = plan.get("stop_loss", "?")
        tp1v      = plan.get("tp1", "?")
        rr        = plan.get("rr_tp1", plan.get("rr", "?"))
        preview   = plan.get("preview_plan") or {}
        veto_reason = plan.get("model_veto_reason")
        if veto_reason:
            print(f"  Plan     : {t_status} | {veto_reason}")
        elif t_status in ("NO_ACTIONABLE_PLAN", "WATCH_ONLY") and preview:
            print(f"  Plan     : {t_status} | preview_only={preview.get('preview_only', False)} | side={preview.get('side', '?')} entry={preview.get('entry_price')} sl={preview.get('stop_loss')} tp1={preview.get('tp1')}")
        else:
            print(f"  Plan     : {t_status} | {direction} | entry={entry} sl={sl} tp1={tp1v} RR={rr}")
    else:
        print(f"  Plan     : (dosya yok)")

    # --- Decision Gate ---
    gate = _read_json(STATE_DIR / "latest_decision_gate.json")
    if gate:
        decision = gate.get("decision", "?")
        reasons = gate.get("block_reasons") or gate.get("warning_reasons") or []
        reason = reasons[0] if reasons else "?"
        print(f"  Gate     : {decision} | {reason}")

    # --- Paper lifecycle ---
    paper = _read_json(STATE_DIR / "latest_paper_lifecycle.json")
    if paper:
        lc_status = paper.get("lifecycle_status", "?")
        side      = paper.get("side", paper.get("direction", "?"))
        entry     = paper.get("entry_price", "?")
        tp1v      = paper.get("tp1", "?")
        sl        = paper.get("stop_loss", "?")
        tp1_hit   = paper.get("tp1_hit", "?")
        sl_hit    = paper.get("stop_hit", "?")
        unreal_r  = paper.get("unrealized_r", "?")
        print(f"  Paper    : {lc_status} | {side} | entry={entry} tp1={tp1v} sl={sl}")
        print(f"             tp1_hit={tp1_hit} | sl_hit={sl_hit} | R={unreal_r}")
    else:
        print(f"  Paper    : (dosya yok)")

    # --- Outcome monitor ---
    outcome = _read_json(STATE_DIR / "latest_outcome_monitor.json")
    if outcome:
        print(f"  Outcome  : {outcome.get('outcome_status', '?')} | {outcome.get('outcome_result', '?')}")

    # --- Edge matrix ---
    edge = _read_json(STATE_DIR / "latest_edge_matrix_v2.json")
    if edge:
        sample_summary = edge.get("sample_summary") or {}
        edge_quality = edge.get("edge_quality") or {}
        samples = sample_summary.get("usable_closed_records", 0)
        e_status = edge_quality.get("edge_status", "?")
        confidence = edge_quality.get("confidence_level", "?")
        print(f"  Edge     : usable_closed={samples} | {e_status} | confidence={confidence}")
    else:
        print(f"  Edge     : (DEGRADED)")

    # --- Kapanan trade ---
    for fname in ("closed_outcomes_with_lineage.jsonl", "closed_paper_outcomes.jsonl"):
        closed_path = DATA_DIR / fname
        if closed_path.exists():
            try:
                lines = [l for l in closed_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                print(f"  Kapanan  : {len(lines)} trade ({fname})")
            except Exception:
                pass
            break

    print(f"{'='*60}")


def main() -> None:
    interval = 30
    cycle = 0

    print("NurNova Pipeline Dongu Basliyor... (v4)")
    print(f"Proje: {ROOT}")
    print(f"Her {interval} saniyede bir calisacak.")
    print("Durdurmak icin Ctrl+C\n")

    while True:
        cycle += 1
        try:
            data = run_once()
            print_summary(data, cycle)
        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            break
        except Exception as ex:
            print(f"\n[HATA] Dongu #{cycle}: {ex}")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            break


if __name__ == "__main__":
    main()
