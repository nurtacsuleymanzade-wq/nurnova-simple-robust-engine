import ast
from pathlib import Path
from collections import defaultdict
from datetime import datetime

target = Path("src/simple/mtf_candle_dna_factory.py")
text = target.read_text(encoding="utf-8")
lines = text.splitlines()

tree = ast.parse(text)

items = []

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        items.append({
            "kind": "function",
            "name": node.name,
            "start": node.lineno,
            "end": getattr(node, "end_lineno", node.lineno)
        })

    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = []
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.append(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                targets.append(node.target.id)

        for name in targets:
            if name.isupper() or name.endswith("_PATH") or name.endswith("_FILE"):
                items.append({
                    "kind": "constant",
                    "name": name,
                    "start": node.lineno,
                    "end": getattr(node, "end_lineno", node.lineno)
                })

by_name = defaultdict(list)
for item in items:
    by_name[(item["kind"], item["name"])].append(item)

duplicates = {k:v for k,v in by_name.items() if len(v) > 1}

remove_ranges = []
report_lines = []
report_lines.append("# CANONICAL DNA FACTORY POWERSHELL CLEANUP REPORT")
report_lines.append("")
report_lines.append(f"Timestamp: {datetime.utcnow().isoformat()}Z")
report_lines.append(f"Target: {target}")
report_lines.append("")
report_lines.append("## Duplicate Definitions Found")
report_lines.append("")

for (kind, name), defs in duplicates.items():
    report_lines.append(f"### {kind}: `{name}`")
    for d in defs:
        marker = "KEEP_LAST" if d is defs[-1] else "REMOVE_SHADOWED"
        report_lines.append(f"- {marker}: lines {d['start']}-{d['end']}")
    report_lines.append("")

    for d in defs[:-1]:
        remove_ranges.append((d["start"], d["end"], kind, name))

if not remove_ranges:
    report_lines.append("No duplicate top-level functions/constants found.")
else:
    remove_set = set()
    for start, end, kind, name in remove_ranges:
        for i in range(start, end + 1):
            remove_set.add(i)

    new_lines = []
    i = 1
    while i <= len(lines):
        if i in remove_set:
            if i == min([r[0] for r in remove_ranges if r[0] <= i <= r[1]], default=i):
                pass
            i += 1
            continue
        new_lines.append(lines[i-1])
        i += 1

    cleaned = "\n".join(new_lines) + "\n"
    target.write_text(cleaned, encoding="utf-8")

report_lines.append("")
report_lines.append("## Cleanup Rule")
report_lines.append("")
report_lines.append("For duplicate top-level functions/constants, earlier shadowed definitions were removed and the last active Python definition was preserved.")
report_lines.append("This preserves current runtime behavior while removing merge-drift ambiguity.")
report_lines.append("")
report_lines.append("## Removed Ranges")
report_lines.append("")

if remove_ranges:
    for start, end, kind, name in remove_ranges:
        report_lines.append(f"- Removed shadowed {kind} `{name}` at lines {start}-{end}")
else:
    report_lines.append("- None")

Path("docs/CANONICAL_DNA_FACTORY_POWERSHELL_CLEANUP.md").write_text("\n".join(report_lines), encoding="utf-8")

print("POWERSHELL_CLEANUP_DONE")
print("Report: docs/CANONICAL_DNA_FACTORY_POWERSHELL_CLEANUP.md")
