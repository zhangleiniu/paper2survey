from __future__ import annotations

import csv
from pathlib import Path

from survey_system.paths import anchors_candidates_csv, anchors_csv


def curate_anchors(topic_path: Path) -> Path:
    candidates_path = anchors_candidates_csv(topic_path, "v1")
    output_path = anchors_csv(topic_path)
    with candidates_path.open("r", encoding="utf-8", newline="") as handle:
        selected = [
            row
            for row in csv.DictReader(handle)
            if row.get("your_decision", "").strip().lower() == "yes"
        ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bib_key", "role_notes"])
        writer.writeheader()
        for row in selected:
            writer.writerow(
                {
                    "bib_key": row["bib_key"],
                    "role_notes": row.get("role_notes") or row.get("llm_reason", ""),
                }
            )
    return output_path
