from __future__ import annotations

import csv
from pathlib import Path

from survey_system.paths import review_needed_csv


def append_review_item(topic_path: Path, bib_key: str, op_name: str, reason: str) -> Path:
    path = review_needed_csv(topic_path)
    path_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bib_key", "op_name", "reason"])
        if not path_exists:
            writer.writeheader()
        writer.writerow({"bib_key": bib_key, "op_name": op_name, "reason": reason})
    return path
