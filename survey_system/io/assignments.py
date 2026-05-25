from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from survey_system.io.outline import section_paths
from survey_system.io.papers import read_papers
from survey_system.paths import section_assignments_path


def inspect_assignments(
    topic_path: Path,
    *,
    low_confidence_below: float = 0.7,
    overloaded_above: int = 5,
) -> dict[str, Any]:
    papers = [paper for paper in read_papers(topic_path) if paper.include == "yes"]
    expected_keys = {paper.bib_key for paper in papers}
    sections = section_paths(topic_path)
    assignments_path = section_assignments_path(topic_path)
    rows = _read_assignment_rows(assignments_path)
    assigned_keys = {row["bib_key"] for row in rows if row.get("bib_key")}
    primary_counts = Counter(row.get("primary_section_path", "") for row in rows)
    section_counts = {section: primary_counts.get(section, 0) for section in sections}
    invalid_primary = [
        row
        for row in rows
        if row.get("primary_section_path") and row.get("primary_section_path") not in sections
    ]
    low_confidence = [
        row
        for row in rows
        if _float_value(row.get("confidence", "0")) < low_confidence_below
    ]
    secondary_count = sum(1 for row in rows if row.get("secondary_section_paths", "").strip())
    empty_sections = [section for section, count in section_counts.items() if count == 0]
    overloaded_sections = [
        {"section": section, "count": count}
        for section, count in section_counts.items()
        if count > overloaded_above
    ]
    missing = sorted(expected_keys - assigned_keys)
    extra = sorted(assigned_keys - expected_keys)
    issues: list[str] = []
    warnings: list[str] = []

    if not assignments_path.exists():
        issues.append(f"missing assignments file: {assignments_path}")
    if missing:
        issues.append(f"missing assignments for papers: {missing}")
    if extra:
        issues.append(f"assignments include non-included papers: {extra}")
    if invalid_primary:
        issues.append(
            "assignments reference primary sections not in outline: "
            + str(sorted({row["primary_section_path"] for row in invalid_primary}))
        )
    if empty_sections:
        warnings.append(f"empty sections: {empty_sections}")
    if overloaded_sections:
        warnings.append(f"overloaded sections: {overloaded_sections}")
    if low_confidence:
        warnings.append(
            "low confidence assignments: "
            + str([row["bib_key"] for row in low_confidence])
        )

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "assigned": len(assigned_keys & expected_keys),
        "total": len(expected_keys),
        "missing": missing,
        "extra": extra,
        "section_counts": section_counts,
        "empty_sections": empty_sections,
        "overloaded_sections": overloaded_sections,
        "low_confidence": low_confidence,
        "secondary_count": secondary_count,
        "invalid_primary": invalid_primary,
        "path": str(assignments_path),
    }


def _read_assignment_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float_value(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0
