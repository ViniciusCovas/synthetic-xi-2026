#!/usr/bin/env python3
"""Run the quota-safe extractor against the conservative selection frontier."""
from pathlib import Path

import scripts.run_targeted_coverage_extraction as targeted


def main() -> None:
    targeted.PRIORITY_PATH = Path(
        "data/model_readiness/selection_frontier_priority_fixtures.csv"
    )
    targeted.main()


if __name__ == "__main__":
    main()
