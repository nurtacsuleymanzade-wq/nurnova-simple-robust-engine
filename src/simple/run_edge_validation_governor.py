from __future__ import annotations

import json

from src.simple.edge_validation_governor import run_edge_validation_governor


def main() -> None:
    print(json.dumps(run_edge_validation_governor(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
