"""Runner for S26B — Live Flow Quality Audit."""

from __future__ import annotations

import json

from src.simple.live_flow_quality_audit import run_live_flow_quality_audit


def main() -> dict:
    result = run_live_flow_quality_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
