"""Read coverage work queues, including legacy blank CSV outputs."""
from pathlib import Path
import pandas as pd

QUEUE_COLUMNS = ["player_id", "fixture_id", "window", "priority_reason",
                 "selection_resolution_reason", "resolved_role"]


def read_coverage_queue(path: Path) -> pd.DataFrame:
    # Only an empty file is a valid no-work condition. Missing files and malformed
    # nonempty schemas remain errors for callers to handle explicitly.
    try:
        frame = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=QUEUE_COLUMNS)
    required = {"player_id", "fixture_id", "window"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Invalid coverage queue {path}: missing {sorted(missing)}")
    return frame
