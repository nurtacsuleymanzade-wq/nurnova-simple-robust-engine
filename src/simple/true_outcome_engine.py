from __future__ import annotations

import json

from src.edge.true_outcome_engine import run_true_outcome_engine


def main() -> None:
    print(json.dumps(run_true_outcome_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
