from __future__ import annotations

import json

from src.edge.edge_learning_dashboard import run_edge_learning_dashboard


def run_edge_learning_report() -> dict[str, object]:
    return run_edge_learning_dashboard()


def main() -> None:
    print(json.dumps(run_edge_learning_report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
