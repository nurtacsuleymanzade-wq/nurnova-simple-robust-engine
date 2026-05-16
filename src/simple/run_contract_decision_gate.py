from __future__ import annotations

import argparse
import json

from src.simple.contract_decision_gate import run_contract_decision_gate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Contract Decision Gate")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    result = run_contract_decision_gate(symbol=args.symbol, fake_sample=args.fake_sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

