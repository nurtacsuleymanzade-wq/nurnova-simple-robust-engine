"""S28 runner — Market Structure V2."""

from __future__ import annotations

import json

from src.simple.market_structure_v2 import run_market_structure_v2, REPORT_PATH


def main() -> dict:
    result = run_market_structure_v2()
    print(f"[S28] structure_bias={result.get('structure_bias')} strength={result.get('structure_strength')}")
    print(f"[S28] bos={result.get('bos_status')} choch={result.get('choch_status')}")
    print(f"[S28] sweep={result.get('liquidity_sweep_status')} hint={result.get('setup_readiness_hint')}")
    print(f"[S28] report -> {REPORT_PATH}")
    print(f"[S28] safe_to_open_real_trade={result['execution_safety']['safe_to_open_real_trade']}")
    return result


if __name__ == "__main__":
    main()
