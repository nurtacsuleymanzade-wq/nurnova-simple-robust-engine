from __future__ import annotations

from src.simple.sample_accumulation_edge_review import REPORT_PATH, run_sample_accumulation_edge_review


def main() -> None:
    result = run_sample_accumulation_edge_review()
    print(f"usable_closed_records : {result['sample_summary']['usable_closed_records']}")
    print(f"current_milestone     : {result['milestone_status']['current_milestone']}")
    print(f"edge_status           : {result['edge_claim_policy']['edge_status']}")
    print(f"edge_claim_allowed    : {result['edge_claim_policy']['edge_claim_allowed']}")
    print(f"recommended_next_fix  : {result['recommended_next_fix']}")
    print(f"report_path           : {REPORT_PATH}")


if __name__ == "__main__":
    main()
