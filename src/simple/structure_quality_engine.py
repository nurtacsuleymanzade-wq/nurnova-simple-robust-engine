from __future__ import annotations

import json

from src.edge.structure_quality_engine import run_structure_quality_engine


def run_passive_structure_quality_engine() -> dict:
    return run_structure_quality_engine()


def main() -> None:
    print(json.dumps(run_passive_structure_quality_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
