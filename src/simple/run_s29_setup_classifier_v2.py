from __future__ import annotations

from src.simple.setup_classifier_v2 import run_setup_classifier_v2, REPORT_PATH


def main() -> None:
    result = run_setup_classifier_v2()
    print(f"setup_status        : {result['setup_status']}")
    print(f"setup_class         : {result['setup_class']}")
    print(f"setup_grade         : {result['setup_grade']}")
    print(f"setup_score         : {result['setup_score']}")
    print(f"setup_confidence    : {result['setup_confidence']}")
    print(f"tradeability        : {result['tradeability']}")
    print(f"report_path         : {REPORT_PATH}")


if __name__ == "__main__":
    main()
