from __future__ import annotations

import json

from src.edge.volume_profile_engine import run_volume_profile_engine


def run_real_volume_profile_engine() -> dict:
    return run_volume_profile_engine()


def main() -> None:
    print(json.dumps(run_real_volume_profile_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
