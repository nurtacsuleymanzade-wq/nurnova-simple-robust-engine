"""
NurNova — Surekli dongu runner v4.
Her 30 saniyede bir pipeline calistirir ve ozet gosterir.
Durdurmak icin: Ctrl+C
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
CANONICAL_RUNTIME = "run_loop.py"
LOCK_PATH = STATE_DIR / "runtime_loop.lock"
TOPOLOGY_REPORT_PATH = ROOT / "runtime_topology_report.json"
LIVE_LOG_PATH = ROOT / "live.log"
LATEST_PIPELINE_FAILURE_PATH = STATE_DIR / "latest_pipeline_failure.json"
REQUIRED_LIVE_LOG_TERMS = ("SEMANTIC", "CLUST", "SETUP_ACT", "PAPER", "EDGE")
LOCK_STALE_SECONDS = 300
PIPELINE_OUTPUT_TAIL_CHARS = 12000
IGNORED_DUPLICATE_CMDLINE_PATTERNS = (
    "grep ",
    " rg ",
    " tee ",
    " cron",
    "crond",
    "--report",
    " reporter",
    "runtime_topology_report",
    "telegram_research_reporter",
)


class _TeeStdout:
    def __init__(self, primary: object, log_path: pathlib.Path) -> None:
        self.primary = primary
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = log_path.open("a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        primary_result = self.primary.write(text)
        self.log_handle.write(text)
        return primary_result

    def flush(self) -> None:
        self.primary.flush()
        self.log_handle.flush()

    def isatty(self) -> bool:
        return bool(getattr(self.primary, "isatty", lambda: False)())

    def reconfigure(self, **kwargs: object) -> None:
        reconfigure = getattr(self.primary, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(**kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self.primary, name)


def _configure_runtime_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(line_buffering=True)
            except Exception:
                pass

    if os.environ.get("NURNOVA_DISABLE_LIVE_LOG_TEE") == "1":
        return
    if not isinstance(sys.stdout, _TeeStdout):
        try:
            sys.stdout = _TeeStdout(sys.stdout, LIVE_LOG_PATH)  # type: ignore[assignment]
        except Exception:
            pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _seconds_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x00100000, False, pid)
            if not handle:
                return False
            try:
                return kernel32.WaitForSingleObject(handle, 0) == 0x00000102
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False


def _scan_proc_run_loops() -> tuple[list[dict], list[str]]:
    proc_root = pathlib.Path("/proc")
    if not proc_root.exists():
        return [], ["PROCFS_NOT_AVAILABLE"]

    matches: list[dict] = []
    errors: list[str] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
        except Exception:
            continue
        if "run_loop.py" not in cmdline and "src.simple.run_loop" not in cmdline:
            continue
        matches.append({
            "pid": int(entry.name),
            "parent_pid": _read_proc_parent_pid(entry / "status"),
            "cmdline": cmdline,
        })
    return matches, errors


def _read_proc_parent_pid(status_path: pathlib.Path) -> int:
    try:
        status = status_path.read_text(encoding="utf-8", errors="ignore")
        ppid_line = next((line for line in status.splitlines() if line.startswith("PPid:")), "")
        return int(ppid_line.split()[1])
    except Exception:
        return 0


def _scan_windows_run_loops() -> tuple[list[dict], list[str]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -match 'python') -and ($_.CommandLine -match 'run_loop\\.py|src\\.simple\\.run_loop') } | "
        "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return [], [f"WINDOWS_PROCESS_SCAN_EXCEPTION_{str(exc)[:120]}"]
    if result.returncode != 0:
        return [], [f"WINDOWS_PROCESS_SCAN_FAILED_{(result.stderr or result.stdout)[:160]}"]
    if not result.stdout.strip():
        return [], []
    try:
        payload = json.loads(result.stdout)
    except Exception as exc:
        return [], [f"WINDOWS_PROCESS_SCAN_JSON_FAILED_{str(exc)[:120]}"]
    records = payload if isinstance(payload, list) else [payload]
    matches = []
    for record in records:
        matches.append({
            "pid": int(record.get("ProcessId") or 0),
            "parent_pid": int(record.get("ParentProcessId") or 0),
            "name": record.get("Name"),
            "cmdline": record.get("CommandLine"),
        })
    return matches, []


def _scan_run_loop_processes() -> tuple[list[dict], list[str]]:
    if os.name == "nt":
        return _scan_windows_run_loops()
    return _scan_proc_run_loops()


def _normalize_cmdline(value: object) -> str:
    return str(value or "").strip()


def _is_ignored_duplicate_candidate(process: dict[str, Any]) -> bool:
    cmdline = f" {_normalize_cmdline(process.get('cmdline')).lower()} "
    return any(pattern in cmdline for pattern in IGNORED_DUPLICATE_CMDLINE_PATTERNS)


def _build_process_index(processes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        int(process.get("pid") or 0): process
        for process in processes
        if int(process.get("pid") or 0) > 0
    }


def _is_ancestor_pid(candidate_pid: int, child_pid: int, process_index: dict[int, dict[str, Any]]) -> bool:
    visited: set[int] = set()
    current_pid = child_pid
    while current_pid and current_pid not in visited:
        visited.add(current_pid)
        record = process_index.get(current_pid)
        if record is None:
            return False
        parent_pid = int(record.get("parent_pid") or 0)
        if parent_pid == candidate_pid:
            return True
        current_pid = parent_pid
    return False


def _is_parent_child_related(candidate_pid: int, current_pid: int, process_index: dict[int, dict[str, Any]]) -> bool:
    return (
        candidate_pid == current_pid
        or _is_ancestor_pid(candidate_pid, current_pid, process_index)
        or _is_ancestor_pid(current_pid, candidate_pid, process_index)
    )


def _read_lock_age_seconds(lock_payload: dict[str, Any]) -> float | None:
    timestamp_fields = (
        lock_payload.get("heartbeat_utc"),
        lock_payload.get("started_at_utc"),
    )
    for raw in timestamp_fields:
        age = _seconds_since(_parse_utc_timestamp(raw))
        if age is not None:
            return age
    try:
        return max(0.0, time.time() - LOCK_PATH.stat().st_mtime)
    except Exception:
        return None


def _refresh_runtime_lock() -> None:
    lock_payload = _read_json(LOCK_PATH)
    if int(lock_payload.get("pid") or 0) != os.getpid():
        return
    lock_payload["heartbeat_utc"] = utc_now()
    _write_json(LOCK_PATH, lock_payload)


def _filter_duplicate_processes(
    detected_processes: list[dict[str, Any]],
    *,
    relation_processes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    current_pid = os.getpid()
    process_index = _build_process_index(relation_processes or detected_processes)
    filtered: list[dict[str, Any]] = []
    seen_pids: set[int] = set()
    for process in detected_processes:
        pid = int(process.get("pid") or 0)
        if pid <= 0 or pid == current_pid:
            continue
        if pid in seen_pids:
            continue
        if _is_ignored_duplicate_candidate(process):
            continue
        if _is_parent_child_related(pid, current_pid, process_index):
            continue
        seen_pids.add(pid)
        filtered.append({
            "pid": pid,
            "parent_pid": int(process.get("parent_pid") or 0),
            "cmdline": _normalize_cmdline(process.get("cmdline")),
            "source": process.get("source", "process_scan"),
        })
    return filtered


def _scan_child_processes() -> tuple[list[dict], list[str]]:
    if os.name == "nt":
        return [], ["CHILD_PROCESS_SCAN_NOT_AVAILABLE_ON_WINDOWS_WITHOUT_CIM"]

    proc_root = pathlib.Path("/proc")
    if not proc_root.exists():
        return [], ["PROCFS_NOT_AVAILABLE"]

    current_pid = os.getpid()
    children: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8", errors="ignore")
            ppid_line = next((line for line in status.splitlines() if line.startswith("PPid:")), "")
            parent_pid = int(ppid_line.split()[1])
            if parent_pid != current_pid:
                continue
            raw = (entry / "cmdline").read_bytes()
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
            children.append({"pid": int(entry.name), "cmdline": cmdline})
        except Exception:
            continue
    return children, []


def _subprocess_usage_report() -> list[dict]:
    return [
        {
            "file": "run_loop.py",
            "usage": "subprocess.run([sys.executable, '-m', 'src.simple.run_local_full_pipeline'], capture_output=True, text=True)",
            "purpose": "one bounded pipeline execution per runtime loop",
            "daemonized_child": False,
            "recursive_run_loop": False,
        },
        {
            "file": "src/simple/run_loop.py",
            "usage": "wrapper only; delegates to root run_loop.py",
            "purpose": "backward-compatible entrypoint",
            "daemonized_child": False,
            "recursive_run_loop": False,
        },
        {
            "file": "src/simple/local_pipeline_runner.py",
            "usage": "contextlib.redirect_stdout for stage JSON parsing",
            "purpose": "capture module main() JSON without spawning child runtimes",
            "daemonized_child": False,
            "recursive_run_loop": False,
        },
        {
            "file": "src/simple/run_local_full_pipeline.py",
            "usage": "direct call to local_pipeline_runner.run_pipeline",
            "purpose": "CLI pipeline entrypoint",
            "daemonized_child": False,
            "recursive_run_loop": False,
        },
    ]


def _live_log_status() -> dict:
    exists = LIVE_LOG_PATH.exists()
    tail = ""
    size = 0
    if exists:
        try:
            size = LIVE_LOG_PATH.stat().st_size
            tail = LIVE_LOG_PATH.read_text(encoding="utf-8", errors="ignore")[-12000:]
        except Exception:
            tail = ""
    present_terms = [term for term in REQUIRED_LIVE_LOG_TERMS if term in tail]
    return {
        "path": str(LIVE_LOG_PATH),
        "exists": exists,
        "size_bytes": size,
        "required_terms": list(REQUIRED_LIVE_LOG_TERMS),
        "present_terms": present_terms,
        "missing_terms": [term for term in REQUIRED_LIVE_LOG_TERMS if term not in present_terms],
        "nohup_only_output": exists and bool(tail.strip()) and tail.strip() == "nohup: ignoring input",
        "stdout_isatty": bool(getattr(sys.stdout, "isatty", lambda: False)()),
    }


def _write_runtime_topology_report(
    *,
    cycle: int,
    duplicate_loop_detected: bool,
    duplicate_loop_fixed: bool,
    duplicate_processes: list[dict],
    process_scan_errors: list[str],
    lock_status: str,
) -> None:
    child_processes, child_scan_errors = _scan_child_processes()
    report = {
        "timestamp_utc": utc_now(),
        "canonical_runtime": CANONICAL_RUNTIME,
        "runtime_pid": os.getpid(),
        "runtime_lock": str(LOCK_PATH),
        "lock_status": lock_status,
        "loop": cycle,
        "child_processes": child_processes,
        "child_process_scan_errors": child_scan_errors,
        "subprocess_usage": _subprocess_usage_report(),
        "duplicate_loop_detected": duplicate_loop_detected,
        "duplicate_loop_fixed": duplicate_loop_fixed,
        "duplicate_processes": duplicate_processes,
        "process_scan_errors": process_scan_errors,
        "live_log_status": _live_log_status(),
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    _write_json(TOPOLOGY_REPORT_PATH, report)


def _acquire_runtime_lock() -> tuple[bool, dict]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    detected_processes, process_scan_errors = _scan_run_loop_processes()
    duplicate_processes = _filter_duplicate_processes(detected_processes)
    duplicate_loop_detected = bool(duplicate_processes)
    duplicate_loop_fixed = False

    existing_lock = _read_json(LOCK_PATH)
    existing_pid = int(existing_lock.get("pid") or 0)
    existing_lock_age_seconds = _read_lock_age_seconds(existing_lock)
    if existing_pid and existing_pid != current_pid:
        lock_pid_seen = any(existing_pid == int(process.get("pid") or 0) for process in detected_processes)
        lock_is_stale = bool(existing_lock_age_seconds is not None and existing_lock_age_seconds > LOCK_STALE_SECONDS)
        if _pid_alive(existing_pid) and (lock_pid_seen or not lock_is_stale):
            duplicate_processes.append({
                "pid": existing_pid,
                "parent_pid": int(existing_lock.get("parent_pid") or 0),
                "cmdline": existing_lock.get("cmdline", "LOCK_FILE_OWNER"),
                "source": "runtime_loop.lock",
            })
            duplicate_loop_detected = True
        else:
            try:
                LOCK_PATH.unlink()
                duplicate_loop_fixed = True
            except FileNotFoundError:
                pass

    duplicate_processes = _filter_duplicate_processes(
        duplicate_processes,
        relation_processes=[*detected_processes, *duplicate_processes],
    )
    duplicate_loop_detected = bool(duplicate_processes)

    if duplicate_loop_detected:
        _write_runtime_topology_report(
            cycle=0,
            duplicate_loop_detected=True,
            duplicate_loop_fixed=duplicate_loop_fixed,
            duplicate_processes=duplicate_processes,
            process_scan_errors=process_scan_errors,
            lock_status="ABORTED_DUPLICATE_RUNTIME",
        )
        return False, {
            "duplicate_loop_detected": True,
            "duplicate_loop_fixed": duplicate_loop_fixed,
            "duplicate_processes": duplicate_processes,
            "process_scan_errors": process_scan_errors,
        }

    lock_payload = {
        "pid": current_pid,
        "parent_pid": os.getppid(),
        "started_at_utc": utc_now(),
        "heartbeat_utc": utc_now(),
        "canonical_runtime": CANONICAL_RUNTIME,
        "cmdline": " ".join(sys.argv),
    }
    try:
        fd = os.open(str(LOCK_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        _write_runtime_topology_report(
            cycle=0,
            duplicate_loop_detected=True,
            duplicate_loop_fixed=duplicate_loop_fixed,
            duplicate_processes=[{"pid": existing_pid, "source": "runtime_loop.lock"}],
            process_scan_errors=process_scan_errors,
            lock_status="ABORTED_LOCK_RACE",
        )
        return False, {
            "duplicate_loop_detected": True,
            "duplicate_loop_fixed": duplicate_loop_fixed,
            "duplicate_processes": [{"pid": existing_pid, "source": "runtime_loop.lock"}],
            "process_scan_errors": process_scan_errors,
        }

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(lock_payload, handle, ensure_ascii=False, indent=2)

    return True, {
        "duplicate_loop_detected": False,
        "duplicate_loop_fixed": duplicate_loop_fixed,
        "duplicate_processes": [],
        "process_scan_errors": process_scan_errors,
    }


def _release_runtime_lock() -> None:
    lock_payload = _read_json(LOCK_PATH)
    if int(lock_payload.get("pid") or 0) != os.getpid():
        return
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def _tail_output(text: str) -> str:
    text = text or ""
    if len(text) <= PIPELINE_OUTPUT_TAIL_CHARS:
        return text
    return text[-PIPELINE_OUTPUT_TAIL_CHARS:]


def _record_pipeline_failure(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    stdout_tail = _tail_output(result.stdout or "")
    stderr_tail = _tail_output(result.stderr or "")
    combined_tail = f"{stdout_tail}\n{stderr_tail}".lower()
    oom_or_killed = result.returncode == 137 or "killed" in combined_tail
    payload = {
        "timestamp_utc": utc_now(),
        "command": [sys.executable, "-m", "src.simple.run_local_full_pipeline"],
        "return_code": result.returncode,
        "last_stdout": stdout_tail,
        "last_stderr": stderr_tail,
        "oom_or_process_killed": oom_or_killed,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    _write_json(LATEST_PIPELINE_FAILURE_PATH, payload)
    if oom_or_killed:
        print("OOM_OR_PROCESS_KILLED", flush=True)
        for item in _largest_runtime_files(limit=20):
            print(f"LARGEST_FILE path={item['path']} size_bytes={item['size_bytes']}", flush=True)
    print("PIPELINE_SUBPROCESS_FAILED", flush=True)
    print(f"return_code={payload['return_code']}", flush=True)
    print(f"last_stdout={payload['last_stdout'] or '<empty>'}", flush=True)
    print(f"last_stderr={payload['last_stderr'] or '<empty>'}", flush=True)
    return payload


def _largest_runtime_files(limit: int = 20) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for root_dir in (STATE_DIR, DATA_DIR):
        if not root_dir.exists():
            continue
        for path in root_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except Exception:
                continue
            files.append({"path": str(path), "size_bytes": size})
    files.sort(key=lambda item: int(item.get("size_bytes") or 0), reverse=True)
    return files[:limit]


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
    if result.returncode != 0:
        failure_payload = _record_pipeline_failure(result)
        return {
            "error": "PIPELINE_SUBPROCESS_FAILED",
            "returncode": result.returncode,
            "last_stdout": failure_payload["last_stdout"],
            "last_stderr": failure_payload["last_stderr"],
            "oom_or_process_killed": failure_payload["oom_or_process_killed"],
        }
    try:
        if LATEST_PIPELINE_FAILURE_PATH.exists():
            try:
                LATEST_PIPELINE_FAILURE_PATH.unlink()
            except FileNotFoundError:
                pass
        return json.loads(result.stdout)
    except Exception:
        return {"error": result.stderr or result.stdout or "bos cikti"}


def _trigger_telegram_instant_report() -> None:
    try:
        subprocess.Popen(
            [sys.executable, "-m", "src.simple.telegram_research_reporter", "--instant"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"TELEGRAM_REPORTER_SOFT_FAIL error={str(exc)[:200]}", flush=True)


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
    sync = _read_json(STATE_DIR / "latest_context_sync.json")
    setup_activation = _read_json(STATE_DIR / "latest_setup_family_activation.json")
    research_lifecycle = _read_json(STATE_DIR / "latest_research_paper_lifecycle.json")
    research_edge = _read_json(STATE_DIR / "latest_research_edge_matrix.json")
    feedback = _read_json(STATE_DIR / "latest_model_feedback.json")
    promotion = _read_json(STATE_DIR / "latest_model_promotion.json")
    live_gate = _read_json(STATE_DIR / "latest_live_eligibility_gate.json")
    audit = _read_json(STATE_DIR / "latest_system_audit.json")
    query_state = _read_json(STATE_DIR / "latest_system_query_state.json")

    print(f"  Pipeline : {es.get('pipeline_status', '?')}")
    print(f"  Bloklar  : {es.get('blocks_passed', 0)}/{es.get('blocks_total', 0)} PASSED")
    print(f"  Veri     : {dq.get('level', '?')} (skor={dq.get('score', 0)})")
    if _legacy_state_present():
        print("  Uyari    : LEGACY_STATE_PRESENT_BUT_IGNORED")

    for blk in data.get("block_results", []):
        if blk.get("status") not in ("PASSED",):
            print(f"  [{blk['status']}] {blk['block_id']}")
            if str(blk.get("block_id") or "").startswith(("OBSERVATION_FACTORY", "MTF_CANDLE_DNA_FACTORY", "ATR_ENGINE", "MARKET_STRUCTURE_ENGINE", "LIQUIDITY_MAP_ENGINE", "INTERPRETATION_ENGINE", "THREE_SCENARIO_ENGINE", "BUSINESS_ZONE_ENGINE", "MARKET_REGIME_CLASSIFIER", "INTENT_ENGINE", "UNIFIED_CONTEXT_ENGINE", "MODEL_DEFINITION_REGISTRY", "MODEL_HUNTER_ENGINE", "MODEL_SEMANTIC_VALIDATOR", "MODEL_CLUSTER_ENGINE", "MODEL_COOLDOWN_ENGINE", "SETUP_FAMILY_ACTIVATION_ENGINE", "PAPER_TRADE_FACTORY", "RESEARCH_PAPER_LIFECYCLE_ENGINE", "RESEARCH_EDGE_MATRIX_ENGINE")):
                print(f"ACTIVE_CHAIN_FAILURE block={blk['block_id']} reason={blk.get('error') or blk.get('status')}")

    print(f"RUNTIME_HEARTBEAT loop={cycle} timestamp={ts}")
    print(
        f"S0_SYNC : {sync.get('sync_status', '?')} "
        f"active_chain_ok={sync.get('active_chain_ok', False)} "
        f"context={sync.get('context_id', '?')} "
        f"mismatch={len(sync.get('context_mismatches') or [])}"
    )
    observation = _read_json(STATE_DIR / "latest_observation_factory.json")
    obs_price = ((observation.get("market_snapshot") or {}).get("price")) if observation else None
    obs_delta = ((observation.get("aggression") or {}).get("delta")) if observation else None
    obs_spread = ((observation.get("market_snapshot") or {}).get("spread")) if observation else None
    print(f"OBS : price={_fmt_value(obs_price)} delta={_fmt_value(obs_delta)} spread={_fmt_value(obs_spread)}")
    mtf_dna = _read_json(STATE_DIR / "latest_mtf_candle_dna.json")
    print(
        f"DNA : 1m={(((mtf_dna.get('1m') or {}).get('candle_category_label')) if mtf_dna else 'UNKNOWN')} "
        f"5m={(((mtf_dna.get('5m') or {}).get('candle_category_label')) if mtf_dna else 'UNKNOWN')} "
        f"15m={(((mtf_dna.get('15m') or {}).get('candle_category_label')) if mtf_dna else 'UNKNOWN')}"
    )
    market_structure = _read_json(STATE_DIR / "latest_market_structure.json")
    print(
        f"STRUCT : 1m={((market_structure.get('1m') or {}).get('structure_label', 'UNKNOWN')) if market_structure else 'UNKNOWN'} "
        f"5m={((market_structure.get('5m') or {}).get('structure_label', 'UNKNOWN')) if market_structure else 'UNKNOWN'} "
        f"15m={((market_structure.get('15m') or {}).get('structure_label', 'UNKNOWN')) if market_structure else 'UNKNOWN'}"
    )
    liquidity_map = _read_json(STATE_DIR / "latest_liquidity_map.json")
    print(
        f"LIQ : near={len((liquidity_map.get('near_liquidity') or [])) if liquidity_map else 0} "
        f"mid={len((liquidity_map.get('mid_liquidity') or [])) if liquidity_map else 0} "
        f"far={len((liquidity_map.get('far_liquidity') or [])) if liquidity_map else 0}"
    )
    semantic_validation = _read_json(STATE_DIR / "latest_model_semantic_validation.json")
    semantic_summary = semantic_validation.get("summary") or {}
    print(
        f"SEMANTIC : valid={semantic_summary.get('validated_count', 0)} "
        f"mixed={semantic_summary.get('mixed_count', 0)} "
        f"hard_blocked={semantic_summary.get('hard_blocked_count', semantic_summary.get('blocked_count', 0))}"
    )
    model_cooldown = _read_json(STATE_DIR / "latest_model_cooldown.json")
    cooldown_summary = model_cooldown.get("summary") or {}
    print(
        f"CLUST : clusters={((_read_json(STATE_DIR / 'latest_model_clusters.json').get('summary') or {}).get('cluster_count', 0))} "
        f"allowed={cooldown_summary.get('allowed_count', 0)} "
        f"cooldown={cooldown_summary.get('blocked_count', 0)}"
    )
    print(
        f"SETUP_ACT : family={setup_activation.get('dominant_setup_family', 'NO_ACTIVE_SETUP_FAMILY')} "
        f"band={setup_activation.get('activation_band', 'WATCH_ONLY')} "
        f"score={_fmt_value(setup_activation.get('activation_score'))} "
        f"ready={setup_activation.get('ready_for_paper_research', False)}"
    )
    lifecycle_summary = research_lifecycle.get("summary") or {}
    print(
        f"PAPER : opened={lifecycle_summary.get('opened', 0)} "
        f"open={lifecycle_summary.get('open', 0)} "
        f"closed={lifecycle_summary.get('closed', 0)} "
        f"invalid={lifecycle_summary.get('invalid', 0)}"
    )
    paper_safety = (_read_json(STATE_DIR / "latest_paper_trade_factory.json").get("paper_safety") or {})
    print(
        f"PAPER_SAFE : conflict_blocked={paper_safety.get('blocked_by_context_direction_conflict', 0)} "
        f"open_limit_blocked={paper_safety.get('blocked_by_open_limit', 0)} "
        f"family_limit_blocked={paper_safety.get('blocked_by_family_limit', 0)}"
    )
    print(
        f"EDGE : status={research_edge.get('edge_status', 'NO_CLOSED_SAMPLES')} "
        f"samples={(research_edge.get('summary') or {}).get('clean_sample_count', 0)} "
        f"best={(research_edge.get('summary') or {}).get('best_model_id', 'UNKNOWN')} "
        f"expectancy={_fmt_value((research_edge.get('summary') or {}).get('best_expectancy'))}"
    )
    print(
        f"FEEDBACK : best={(feedback.get('summary') or {}).get('best', 'UNKNOWN')} "
        f"worst={(feedback.get('summary') or {}).get('worst', 'UNKNOWN')} "
        f"sample_building={(feedback.get('summary') or {}).get('sample_building', 0)}"
    )
    promotion_summary = promotion.get("promotion_summary") or {}
    print(
        f"PROMOTION : watchlist={promotion_summary.get('watchlist', 0)} "
        f"probation={promotion_summary.get('probation', 0)} "
        f"paper_validated={promotion_summary.get('paper_validated', 0)} "
        f"live_diag={promotion_summary.get('live_eligible_diagnostic_only', 0)} "
        f"rejected={promotion_summary.get('rejected', 0)}"
    )
    print(
        f"LIVE_GATE : live_enabled={live_gate.get('live_enabled', False)} "
        f"eligible_diag={live_gate.get('eligible_diag', False)} "
        f"blocked={len(live_gate.get('blocked_models') or [])}"
    )
    print(
        f"AUDIT : status={audit.get('system_status', 'UNKNOWN')} "
        f"score={audit.get('score_100', '?')} "
        f"critical={len(audit.get('critical_issues') or [])} "
        f"warnings={len(audit.get('warnings') or [])}"
    )
    print(
        f"QUERY : ready={query_state.get('query_ready', False)} "
        f"bottleneck={query_state.get('bottleneck', 'UNKNOWN')}"
    )
    print("SAFETY : live_order_sent=false private_api=false")
    print(f"{'='*60}")


def main() -> None:
    _configure_runtime_output()
    lock_acquired, topology = _acquire_runtime_lock()
    if not lock_acquired:
        print("DUPLICATE_RUNTIME_DETECTED", flush=True)
        print(
            "CANONICAL_RUNTIME_ABORTED duplicate_loop_detected=True "
            f"timestamp={utc_now()} report={TOPOLOGY_REPORT_PATH}",
            flush=True,
        )
        raise SystemExit(2)

    interval = float(os.environ.get("NURNOVA_LOOP_INTERVAL_SECONDS", "30"))
    max_cycles_raw = os.environ.get("NURNOVA_LOOP_MAX_CYCLES", "").strip()
    max_cycles = int(max_cycles_raw) if max_cycles_raw.isdigit() and int(max_cycles_raw) > 0 else None
    cycle = 0

    print(
        f"CANONICAL_RUNTIME_STARTED pid={os.getpid()} canonical={CANONICAL_RUNTIME} timestamp={utc_now()}",
        flush=True,
    )
    print("NurNova Pipeline Dongu Basliyor... (v4)", flush=True)
    print(f"Proje: {ROOT}", flush=True)
    print(f"Her {interval:g} saniyede bir calisacak.", flush=True)
    print("Durdurmak icin Ctrl+C\n", flush=True)

    try:
        while True:
            cycle += 1
            print(f"RUNTIME_HEARTBEAT loop={cycle} timestamp={utc_now()}", flush=True)
            try:
                data = run_once()
                print_summary(data, cycle)
                _trigger_telegram_instant_report()
                if data.get("oom_or_process_killed"):
                    break
            except KeyboardInterrupt:
                print("\nDongu durduruldu.", flush=True)
                break
            except Exception as ex:
                print(f"\n[HATA] Dongu #{cycle}: {ex}", flush=True)
                _trigger_telegram_instant_report()

            _write_runtime_topology_report(
                cycle=cycle,
                duplicate_loop_detected=bool(topology.get("duplicate_loop_detected")),
                duplicate_loop_fixed=bool(topology.get("duplicate_loop_fixed")),
                duplicate_processes=list(topology.get("duplicate_processes") or []),
                process_scan_errors=list(topology.get("process_scan_errors") or []),
                lock_status="RUNNING",
            )
            _refresh_runtime_lock()

            if max_cycles is not None and cycle >= max_cycles:
                break

            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\nDongu durduruldu.", flush=True)
                break
    finally:
        _write_runtime_topology_report(
            cycle=cycle,
            duplicate_loop_detected=bool(topology.get("duplicate_loop_detected")),
            duplicate_loop_fixed=bool(topology.get("duplicate_loop_fixed")),
            duplicate_processes=list(topology.get("duplicate_processes") or []),
            process_scan_errors=list(topology.get("process_scan_errors") or []),
            lock_status="STOPPED",
        )
        _release_runtime_lock()
        print(
            f"CANONICAL_RUNTIME_STOPPED pid={os.getpid()} canonical={CANONICAL_RUNTIME} timestamp={utc_now()}",
            flush=True,
        )


if __name__ == "__main__":
    main()
