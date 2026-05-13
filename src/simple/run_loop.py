"""Compatibility wrapper for the canonical root runtime loop."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CANONICAL_RUNTIME_PATH = ROOT / "run_loop.py"


def _load_canonical_runtime():
    spec = importlib.util.spec_from_file_location("_nurnova_canonical_run_loop", CANONICAL_RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical runtime: {CANONICAL_RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    runtime = _load_canonical_runtime()
    runtime.main()


if __name__ == "__main__":
    main()
