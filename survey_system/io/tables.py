from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from survey_system.io.outline import parse_outline
from survey_system.io.papers import read_papers
from survey_system.io.schemas import load_current_schema
from survey_system.paths import (
    outline_path,
    paper_l0_path,
    paper_l1_path,
    paper_l2_path,
    paper_l3_path,
    paper_matrix_csv,
    paper_meta_path,
    paper_status_csv,
    pdfs_dir,
    section_assignments_path,
)
from survey_system.status import _review_item_is_stale, _review_rows


PAPER_STATUS_FIELDS = [
    "bib_key",
    "title",
    "year",
    "venue",
    "included",
    "pdf_exists",
    "L0_exists",
    "L0_chars",
    "meta_exists",
    "paper_type",
    "triage_confidence",
    "L3_exists",
    "L3_chars",
    "L1_exists",
    "L1_schema_version",
    "L2_exists",
    "L2_words",
    "primary_section",
    "secondary_sections",
    "assignment_confidence",
    "bundle_file",
    "active_review_reasons",
    "stale_review_reasons",
]

PAPER_MATRIX_FIXED_FIELDS = [
    "bib_key",
    "title",
    "year",
    "venue",
    "paper_type",
    "primary_section",
    "secondary_sections",
    "tldr",
    "topics",
    "L1_schema_version",
]


def write_paper_status_table(topic_path: Path) -> Path:
    path = paper_status_csv(topic_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = paper_status_rows(topic_path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAPER_STATUS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_paper_matrix_table(topic_path: Path) -> Path:
    path = paper_matrix_csv(topic_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, fieldnames = paper_matrix_rows(topic_path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def paper_status_rows(topic_path: Path) -> list[dict[str, str]]:
    assignments = _assignment_rows_by_key(topic_path)
    bundle_by_section = _bundle_paths_by_section(topic_path)
    review_by_key = _review_reasons_by_key(topic_path)
    rows: list[dict[str, str]] = []

    for paper in read_papers(topic_path):
        bib_key = paper.bib_key
        meta = _read_json(paper_meta_path(topic_path, bib_key))
        l1 = _read_json(paper_l1_path(topic_path, bib_key))
        assignment = assignments.get(bib_key, {})
        primary_section = assignment.get("primary_section_path", "")
        l0_path = paper_l0_path(topic_path, bib_key)
        l2_path = paper_l2_path(topic_path, bib_key)
        l3_path = paper_l3_path(topic_path, bib_key)

        rows.append(
            {
                "bib_key": bib_key,
                "title": paper.title,
                "year": str(paper.year),
                "venue": paper.venue,
                "included": paper.include,
                "pdf_exists": _bool_text((pdfs_dir(topic_path) / paper.pdf_filename).exists()),
                "L0_exists": _bool_text(l0_path.exists()),
                "L0_chars": str(_text_len(l0_path)),
                "meta_exists": _bool_text(bool(meta)),
                "paper_type": str(meta.get("paper_type", "") if meta else ""),
                "triage_confidence": str(meta.get("paper_type_confidence", "") if meta else ""),
                "L3_exists": _bool_text(l3_path.exists()),
                "L3_chars": str(_text_len(l3_path)),
                "L1_exists": _bool_text(bool(l1)),
                "L1_schema_version": str(l1.get("_schema_version", "") if l1 else ""),
                "L2_exists": _bool_text(l2_path.exists()),
                "L2_words": str(_word_count(l2_path)),
                "primary_section": primary_section,
                "secondary_sections": assignment.get("secondary_section_paths", ""),
                "assignment_confidence": assignment.get("confidence", ""),
                "bundle_file": bundle_by_section.get(primary_section, ""),
                "active_review_reasons": "; ".join(review_by_key["active"].get(bib_key, [])),
                "stale_review_reasons": "; ".join(review_by_key["stale"].get(bib_key, [])),
            }
        )

    return rows


def paper_matrix_rows(topic_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    schema = load_current_schema(topic_path)
    universal_fields = _schema_property_names(schema.universal)
    type_fields_by_type = {
        paper_type: _schema_property_names(type_schema)
        for paper_type, type_schema in schema.by_type.items()
    }
    dynamic_fields = [f"universal.{field}" for field in universal_fields]
    for paper_type in sorted(type_fields_by_type):
        dynamic_fields.extend(
            f"type_specific.{paper_type}.{field}" for field in type_fields_by_type[paper_type]
        )

    fieldnames = PAPER_MATRIX_FIXED_FIELDS + dynamic_fields
    assignments = _assignment_rows_by_key(topic_path)
    rows: list[dict[str, str]] = []

    for paper in read_papers(topic_path):
        if paper.include != "yes":
            continue
        bib_key = paper.bib_key
        meta = _read_json(paper_meta_path(topic_path, bib_key))
        l1 = _read_json(paper_l1_path(topic_path, bib_key))
        assignment = assignments.get(bib_key, {})
        paper_type = str((l1.get("_paper_type") if l1 else "") or (meta.get("paper_type", "") if meta else ""))
        row = {field: "" for field in fieldnames}
        row.update(
            {
                "bib_key": bib_key,
                "title": paper.title,
                "year": str(paper.year),
                "venue": paper.venue,
                "paper_type": paper_type,
                "primary_section": assignment.get("primary_section_path", ""),
                "secondary_sections": assignment.get("secondary_section_paths", ""),
                "tldr": _format_cell(meta.get("tldr", "") if meta else ""),
                "topics": _format_cell(meta.get("topics", []) if meta else []),
                "L1_schema_version": str(l1.get("_schema_version", "") if l1 else ""),
            }
        )
        for field in universal_fields:
            row[f"universal.{field}"] = _format_cell(l1.get("universal", {}).get(field, "") if l1 else "")
        if paper_type in type_fields_by_type:
            for field in type_fields_by_type[paper_type]:
                row[f"type_specific.{paper_type}.{field}"] = _format_cell(
                    l1.get("type_specific", {}).get(field, "") if l1 else ""
                )
        rows.append(row)

    return rows, fieldnames


def write_all_tables(topic_path: Path) -> list[Path]:
    return [write_paper_status_table(topic_path), write_paper_matrix_table(topic_path)]


def _assignment_rows_by_key(topic_path: Path) -> dict[str, dict[str, str]]:
    path = section_assignments_path(topic_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["bib_key"]: row for row in csv.DictReader(handle) if row.get("bib_key")}


def _bundle_paths_by_section(topic_path: Path) -> dict[str, str]:
    if not outline_path(topic_path).exists():
        return {}
    bundle_by_section: dict[str, str] = {}
    for index, section in enumerate(parse_outline(topic_path), start=1):
        bundle_by_section[section.path] = f"bundles/section_{index:02d}_{section.slug}.md"
    return bundle_by_section


def _review_reasons_by_key(topic_path: Path) -> dict[str, dict[str, list[str]]]:
    reasons = {"active": {}, "stale": {}}
    for row in _review_rows(topic_path):
        bib_key = row.get("bib_key", "")
        if not bib_key:
            continue
        bucket = "stale" if _review_item_is_stale(topic_path, row) else "active"
        reasons[bucket].setdefault(bib_key, []).append(
            f"{row.get('op_name', '')}: {row.get('reason', '')}".strip(": ")
        )
    return reasons


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _text_len(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8"))


def _word_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").split())


def _schema_property_names(schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return []
    return list(properties)


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_format_cell(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _bool_text(value: bool) -> str:
    return "yes" if value else "no"
