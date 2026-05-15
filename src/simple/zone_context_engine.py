from __future__ import annotations

import json

from src.edge.zone_engine import run_zone_engine


def run_zone_context_engine() -> dict:
    return run_zone_engine()


def main() -> None:
    print(json.dumps(run_zone_context_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
