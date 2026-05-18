import json, os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

BASE = Path("/root/nurnova-simple-robust-engine")
DATA = BASE / "data/simple/epoch_v2"
STATE = BASE / "state/simple/epoch_v2"

def load_jsonl(path, max_lines=5000):
    records = []
    try:
        with open(path) as f:
            for i, line in enumerate(f):
                if i >= max_lines: break
                line = line.strip()
                if line:
                    try: records.append(json.loads(line))
                    except: pass
    except: pass
    return records

def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def avg(lst): return sum(lst)/len(lst) if lst else 0

SEP = "="*65

print("Veriler yukleniyor...")
paper_trades  = load_jsonl(DATA / "paper_trade_factory_history.jsonl")
true_outcomes = load_jsonl(DATA / "true_outcome_history.jsonl")
signal_grades = load_jsonl(DATA / "signal_grade_history.jsonl")
full_lineage  = load_jsonl(DATA / "full_lineage_history.jsonl")
tp_dna        = load_jsonl(DATA / "tp_condition_dna_history.jsonl")
outcome_acct  = load_jsonl(DATA / "outcome_accounting_history.jsonl")
regime_hist   = load_jsonl(DATA / "regime_classifier_history.jsonl")
research_lc   = load_jsonl(DATA / "research_paper_lifecycle_history.jsonl")
edge_matrix   = load_jsonl(DATA / "contract_edge_matrix_history.jsonl")
signal_events = load_jsonl(DATA / "signal_event_history.jsonl")
true_edge     = load_jsonl(DATA / "true_edge_dataset_history.jsonl")

print(f"paper_trades:  {len(paper_trades)}")
print(f"true_outcomes: {len(true_outcomes)}")
print(f"signal_grades: {len(signal_grades)}")
print(f"full_lineage:  {len(full_lineage)}")
print(f"tp_dna:        {len(tp_dna)}")
print(f"outcome_acct:  {len(outcome_acct)}")
print(f"research_lc:   {len(research_lc)}")
print(f"edge_matrix:   {len(edge_matrix)}")
print(f"signal_events: {len(signal_events)}")
print(f"true_edge:     {len(true_edge)}")

# lineage map
lineage_map = {}
for r in full_lineage:
    tid = r.get("trade_id") or r.get("contract_id")
    if tid: lineage_map[tid] = r

grade_map = {}
for r in signal_grades:
    tid = r.get("trade_id") or r.get("contract_id") or r.get("signal_id")
    if tid: grade_map[tid] = r

paper_map = {}
for r in paper_trades:
    tid = r.get("trade_id") or r.get("contract_id")
    if tid: paper_map[tid] = r

TP_VALS = {"TP1","TP2","TP","tp1","tp2","tp","TP1_HIT","TP2_HIT"}
SL_VALS = {"SL","sl","STOP","stop","SL_HIT"}

tp_records = [r for r in true_outcomes if r.get("outcome") in TP_VALS]
sl_records = [r for r in true_outcomes if r.get("outcome") in SL_VALS]

print(f"\n{SEP}")
print("Q1: OUTCOME DAGILI MI")
print(SEP)
outcome_counts = Counter(r.get("outcome","UNKNOWN") for r in true_outcomes)
for k,v in outcome_counts.most_common():
    print(f"  {k}: {v}")
print(f"  TOPLAM: {len(true_outcomes)}, TP={len(tp_records)}, SL={len(sl_records)}")

print(f"\n{SEP}")
print("Q1b: TP OLAN MODELLER")
print(SEP)
tp_models = Counter()
sl_models = Counter()
all_models = Counter()
for r in true_outcomes:
    m = r.get("model") or r.get("setup_model","?")
    o = r.get("outcome","")
    all_models[m] += 1
    if o in TP_VALS: tp_models[m] += 1
    elif o in SL_VALS: sl_models[m] += 1

for m,c in tp_models.most_common(15):
    sl_c = sl_models.get(m,0)
    total = c+sl_c
    wr = c/total*100 if total else 0
    print(f"  {m}: TP={c} SL={sl_c} WR={wr:.0f}%")

if not tp_models:
    print("  *** TP olan model yok veya outcome bos ***")
    if true_outcomes:
        print(f"  Ornek kayit: {json.dumps(true_outcomes[-1], ensure_ascii=False)[:500]}")

print(f"\n{SEP}")
print("Q2: TP vs SL - NUMERIC DIFF")
print(SEP)
tp_feat = defaultdict(list)
sl_feat = defaultdict(list)
keys_to_check = ["rr1","rr2","confluence_count","spread","delta","imbalance_score",
                 "structure_score","quality_score","grade_score","atr","volume",
                 "entry_price","sl_price","tp1_price","rr","score","quality"]
for r in true_outcomes:
    o = r.get("outcome","")
    is_tp = o in TP_VALS
    is_sl = o in SL_VALS
    for key in keys_to_check:
        val = r.get(key)
        if val is not None:
            try:
                fval = float(val)
                if is_tp: tp_feat[key].append(fval)
                elif is_sl: sl_feat[key].append(fval)
            except: pass

found_any = False
for key in keys_to_check:
    if tp_feat[key] or sl_feat[key]:
        found_any = True
        tp_a = avg(tp_feat[key])
        sl_a = avg(sl_feat[key])
        print(f"  {key:<25} TP={tp_a:.4f} SL={sl_a:.4f} diff={tp_a-sl_a:+.4f}")
if not found_any:
    print("  *** Numeric diff icin veri yok ***")
    if true_outcomes:
        print(f"  true_outcome fields: {list(true_outcomes[-1].keys())}")

print(f"\n{SEP}")
print("Q3: DUPLICATE TRADE")
print(SEP)
fingerprints = defaultdict(list)
for r in paper_trades:
    ts = str(r.get("timestamp",""))[:16]
    m = r.get("model") or r.get("setup_model","?")
    d = r.get("direction","?")
    tid = r.get("trade_id") or r.get("contract_id","?")
    fingerprints[f"{ts}|{m}|{d}"].append(tid)

dups = {fp:tids for fp,tids in fingerprints.items() if len(tids)>1}
print(f"  Unique fingerprint: {len(fingerprints)}")
print(f"  Duplicate:          {len(dups)}")
for fp,tids in list(dups.items())[:5]:
    print(f"  {fp} -> {tids}")

print(f"\n{SEP}")
print("Q4: HIZLI TP - MODEL BAZLI")
print(SEP)
model_times = defaultdict(list)
for r in true_outcomes:
    if r.get("outcome") not in TP_VALS: continue
    m = r.get("model") or r.get("setup_model","?")
    for tf in ["minutes_to_tp","duration_minutes","candles_to_tp","bars_to_tp"]:
        v = r.get(tf)
        if v is not None:
            try: model_times[m].append(float(v)); break
            except: pass
if model_times:
    for m,times in sorted(model_times.items(), key=lambda x: avg(x[1])):
        print(f"  {m}: avg={avg(times):.1f} min, n={len(times)}")
else:
    print("  *** Timing verisi yok ***")

print(f"\n{SEP}")
print("Q5: MAE (ADVERSE EXCURSION)")
print(SEP)
mae_data = defaultdict(list)
for r in true_outcomes:
    o = r.get("outcome","?")
    for mkey in ["mae","max_adverse_excursion","adverse_excursion","drawdown"]:
        v = r.get(mkey)
        if v is not None:
            try: mae_data[o].append(float(v)); break
            except: pass
if mae_data:
    for o,vals in sorted(mae_data.items()):
        print(f"  {o}: avg={avg(vals):.4f} max={max(vals):.4f} n={len(vals)}")
else:
    print("  *** MAE verisi yok ***")

print(f"\n{SEP}")
print("Q6: LIQUIDITY vs WR")
print(SEP)
liq_stats = defaultdict(lambda:{"tp":0,"sl":0})
for r in true_outcomes:
    o = r.get("outcome","")
    liq = r.get("liquidity_condition") or r.get("liq_condition") or r.get("liquidity_state","?")
    if liq=="?":
        tid = r.get("trade_id") or r.get("contract_id")
        liq = lineage_map.get(tid,{}).get("liquidity_condition","?")
    if o in TP_VALS: liq_stats[liq]["tp"]+=1
    elif o in SL_VALS: liq_stats[liq]["sl"]+=1
found = [(l,s) for l,s in liq_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for liq,s in sorted(found, key=lambda x: x[1]["tp"]+x[1]["sl"], reverse=True):
        t=s["tp"]+s["sl"]
        print(f"  {liq}: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** Liquidity verisi yok ***")

print(f"\n{SEP}")
print("Q7: TIMEFRAME vs WR")
print(SEP)
tf_stats = defaultdict(lambda:{"tp":0,"sl":0})
for r in true_outcomes:
    o = r.get("outcome","")
    tf = r.get("primary_tf") or r.get("timeframe") or r.get("tf","?")
    if o in TP_VALS: tf_stats[tf]["tp"]+=1
    elif o in SL_VALS: tf_stats[tf]["sl"]+=1
found = [(t,s) for t,s in tf_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for tf,s in sorted(found, key=lambda x: x[1]["tp"]+x[1]["sl"], reverse=True):
        t=s["tp"]+s["sl"]
        print(f"  {tf}: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** TF verisi yok, lineage'dan deniyorum ***")
    for r in true_outcomes:
        o = r.get("outcome","")
        tid = r.get("trade_id") or r.get("contract_id")
        lin = lineage_map.get(tid,{})
        tf = lin.get("primary_tf") or lin.get("timeframe","?")
        if o in TP_VALS: tf_stats[tf]["tp"]+=1
        elif o in SL_VALS: tf_stats[tf]["sl"]+=1
    for tf,s in sorted(tf_stats.items(), key=lambda x: x[1]["tp"]+x[1]["sl"], reverse=True)[:10]:
        t=s["tp"]+s["sl"]
        if t==0: continue
        print(f"  {tf}: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")

print(f"\n{SEP}")
print("Q8: CONFLUENCE vs WR")
print(SEP)
conf_stats = defaultdict(lambda:{"tp":0,"sl":0})
for r in true_outcomes:
    o = r.get("outcome","")
    c = r.get("confluence_count") or r.get("confluence_score")
    if c is None:
        tid = r.get("trade_id") or r.get("contract_id")
        c = lineage_map.get(tid,{}).get("confluence_count")
    if c is not None:
        try: bucket=int(float(c))
        except: bucket=-1
        if o in TP_VALS: conf_stats[bucket]["tp"]+=1
        elif o in SL_VALS: conf_stats[bucket]["sl"]+=1
found = [(k,s) for k,s in conf_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for cnt,s in sorted(found):
        t=s["tp"]+s["sl"]
        print(f"  confluence={cnt}: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** Confluence verisi yok ***")

print(f"\n{SEP}")
print("Q9: REGIME vs WR")
print(SEP)
reg_stats = defaultdict(lambda:{"tp":0,"sl":0})
for r in true_outcomes:
    o = r.get("outcome","")
    reg = r.get("regime") or r.get("market_regime","?")
    if reg=="?":
        tid = r.get("trade_id") or r.get("contract_id")
        reg = lineage_map.get(tid,{}).get("regime","?")
    if o in TP_VALS: reg_stats[reg]["tp"]+=1
    elif o in SL_VALS: reg_stats[reg]["sl"]+=1
found = [(r,s) for r,s in reg_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for reg,s in sorted(found, key=lambda x: x[1]["tp"]+x[1]["sl"], reverse=True):
        t=s["tp"]+s["sl"]
        print(f"  {reg}: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** Regime verisi yok ***")

print(f"\n{SEP}")
print("Q10: MODEL CLUSTERING")
print(SEP)
all_model_names = set()
for r in paper_trades+true_outcomes:
    m = r.get("model") or r.get("setup_model","")
    if m: all_model_names.add(m)
print(f"  Toplam unique model: {len(all_model_names)}")
groups = defaultdict(list)
for m in sorted(all_model_names):
    u = m.upper()
    if any(x in u for x in ["REVERSAL","TRAP","FCR","SWEEP","FAKE"]):
        groups["REVERSAL"].append(m)
    elif any(x in u for x in ["CONTINUATION","TREND","MOMENTUM"]):
        groups["CONTINUATION"].append(m)
    elif any(x in u for x in ["DISTRIBUTION","ABSORPTION","DOUBLE"]):
        groups["DISTRIBUTION"].append(m)
    elif any(x in u for x in ["STRUCTURE","BOS","BREAK","FLOW","ALIGN"]):
        groups["STRUCTURE_FLOW"].append(m)
    else:
        groups["OTHER"].append(m)
for grp,models in groups.items():
    print(f"\n  [{grp}] ({len(models)}):")
    for m in models:
        tp=tp_models.get(m,0); sl=sl_models.get(m,0); t=tp+sl
        wr=tp/t*100 if t else 0
        print(f"    {m}: TP={tp} SL={sl} WR={wr:.0f}%")

print(f"\n{SEP}")
print("Q12: SAAT vs WR (UTC)")
print(SEP)
hour_stats = defaultdict(lambda:{"tp":0,"sl":0})
for r in true_outcomes:
    o = r.get("outcome","")
    ts = r.get("timestamp") or r.get("open_time") or r.get("created_at","")
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z",""))
        h = dt.hour
    except: continue
    if o in TP_VALS: hour_stats[h]["tp"]+=1
    elif o in SL_VALS: hour_stats[h]["sl"]+=1
found = [(h,s) for h,s in hour_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for h,s in sorted(found):
        t=s["tp"]+s["sl"]
        sess = "Asia" if h<8 else ("London" if h<16 else "NY")
        print(f"  {h:02d}:00 [{sess}]: TP={s['tp']} SL={s['sl']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** Saat verisi yok ***")

print(f"\n{SEP}")
print("Q14: GRADE AUDIT (A+ gercekten A+ mi?)")
print(SEP)
grade_stats = defaultdict(lambda:{"tp":0,"sl":0,"open":0})
for r in true_outcomes:
    o = r.get("outcome","")
    g = r.get("grade","?")
    if g=="?":
        tid = r.get("trade_id") or r.get("contract_id")
        g = grade_map.get(tid,{}).get("grade","?")
    if o in TP_VALS: grade_stats[g]["tp"]+=1
    elif o in SL_VALS: grade_stats[g]["sl"]+=1
    else: grade_stats[g]["open"]+=1
found = [(g,s) for g,s in grade_stats.items() if s["tp"]+s["sl"]>0]
if found:
    for g,s in sorted(found, key=lambda x:x[0]):
        t=s["tp"]+s["sl"]
        print(f"  {g}: TP={s['tp']} SL={s['sl']} OPEN={s['open']} WR={s['tp']/t*100:.0f}%")
else:
    print("  *** Grade verisi yok ***")
    if signal_grades:
        print(f"  Signal grade ornek: {json.dumps(signal_grades[-1], ensure_ascii=False)[:300]}")

print(f"\n{SEP}")
print("Q15: OUTCOME ACCOUNTING DURUMU")
print(SEP)
latest_acct = load_json(STATE / "latest_outcome_accounting.json")
latest_paper = load_json(STATE / "latest_paper_trade_factory.json")
latest_outcome_s = load_json(STATE / "latest_true_outcome.json")
print(f"  Outcome accounting: {json.dumps(latest_acct, ensure_ascii=False)[:500]}")
print(f"\n  Latest paper trade: {json.dumps(latest_paper, ensure_ascii=False)[:500]}")
print(f"\n  Latest true outcome: {json.dumps(latest_outcome_s, ensure_ascii=False)[:500]}")

print(f"\n{SEP}")
print("KRITIK OZET")
print(SEP)
print(f"  paper_trades:  {len(paper_trades)}")
print(f"  true_outcomes: {len(true_outcomes)}")
print(f"  TP:            {len(tp_records)}")
print(f"  SL:            {len(sl_records)}")
print(f"  OPEN:          {len(true_outcomes)-len(tp_records)-len(sl_records)}")
if len(tp_records)+len(sl_records)>0:
    wr=(len(tp_records)/(len(tp_records)+len(sl_records)))*100
    print(f"  GENEL WR:      {wr:.1f}%")
else:
    print("  *** HENUZ KAPALI TRADE YOK ***")

# En cok kayit olan dosyalarin son kaydi
print(f"\n  --- SAMPLE: son true_outcome ---")
if true_outcomes:
    print(json.dumps(true_outcomes[-1], ensure_ascii=False, indent=2)[:800])
print(f"\n  --- SAMPLE: son paper_trade ---")
if paper_trades:
    print(json.dumps(paper_trades[-1], ensure_ascii=False, indent=2)[:800])
print(f"\n  --- SAMPLE: son research_lc ---")
if research_lc:
    print(json.dumps(research_lc[-1], ensure_ascii=False, indent=2)[:800])

print(f"\n{SEP}")
print("AUDIT TAMAMLANDI")
print(SEP)
