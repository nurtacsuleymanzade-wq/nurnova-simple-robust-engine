import time
import subprocess
import sys

BASE = "/root/nurnova-simple-robust-engine"
PY = f"{BASE}/.venv/bin/python3"

def run(module, timeout=120):
    try:
        subprocess.run([PY, "-m", module], timeout=timeout, cwd=BASE)
        print(f"OK: {module}")
    except Exception as e:
        print(f"ERR {module}: {e}")

while True:
    print("[RESEARCH] Starting cycle...")
    run("src.simple.research_edge_matrix_engine", timeout=120)
    run("src.simple.outcome_accounting_engine", timeout=60)
    run("src.simple.true_outcome_engine", timeout=60)
    print("[RESEARCH] Cycle done. Sleeping 15min...")
    time.sleep(900)
