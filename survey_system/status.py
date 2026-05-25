from __future__ import annotations

import csv
from pathlib import Path

from survey_system.config import load_config
from survey_system.io.outline import parse_outline
from survey_system.io.papers import read_papers
from survey_system.io.runlog import recent_runs
from survey_system.paths import (
    anchors_csv,
    bundles_dir,
    outline_path,
    paper_l0_path,
    paper_l1_path,
    paper_l2_path,
    paper_l3_path,
    paper_meta_path,
    review_needed_csv,
    section_assignments_path,
)


def topic_status(topic_path: Path, detailed: bool = False) -> dict[str, object]:
    config = load_config(topic_path)
    papers = [paper for paper in read_papers(topic_path) if paper.include == "yes"]
    review_rows = _review_rows(topic_path)
    review_summary = _review_summary(topic_path, review_rows)
    rounds = {
        "round0": _count_existing(topic_path, papers, paper_l0_path),
        "round1_meta": _count_existing(topic_path, papers, paper_meta_path),
        "round1_l3": _count_existing(topic_path, papers, paper_l3_path),
        "round2_anchors": {"complete": anchors_csv(topic_path).exists(), "path": str(anchors_csv(topic_path))},
        "round4_l1": _count_existing(topic_path, papers, paper_l1_path),
        "round4_l2": _count_existing(topic_path, papers, paper_l2_path),
        "round5_outline": {"complete": outline_path(topic_path).exists(), "path": str(outline_path(topic_path))},
        "round6_assignments": _assignment_status(topic_path, papers),
        "round6_bundles": _bundle_status(topic_path),
    }
    status: dict[str, object] = {
        "topic_name": config.topic_name,
        "included_papers": len(papers),
        "review_queue_items": len(review_rows),
        "active_review_items": len(review_summary["active"]),
        "stale_review_items": len(review_summary["stale"]),
        "suggested_next_op": _suggest_next(rounds),
        "rounds": rounds,
        "recent_runs": recent_runs(topic_path),
    }
    if detailed:
        status["review_items"] = review_rows
        status["active_review_items_detail"] = review_summary["active"]
        status["stale_review_items_detail"] = review_summary["stale"]
    return status


def _count_existing(topic_path: Path, papers, path_func) -> dict[str, object]:
    count = sum(1 for paper in papers if path_func(topic_path, paper.bib_key).exists())
    return {"complete": count == len(papers) and len(papers) > 0, "count": count, "total": len(papers)}


def _review_rows(topic_path: Path) -> list[dict[str, str]]:
    path = review_needed_csv(topic_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _review_summary(topic_path: Path, rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    active: list[dict[str, str]] = []
    stale: list[dict[str, str]] = []
    for row in rows:
        if _review_item_is_stale(topic_path, row):
            stale.append(row)
        else:
            active.append(row)
    return {"active": active, "stale": stale}


def _review_item_is_stale(topic_path: Path, row: dict[str, str]) -> bool:
    bib_key = row.get("bib_key", "")
    op_name = row.get("op_name", "")
    reason = row.get("reason", "")
    if not bib_key:
        return False

    if op_name == "parse_pdf":
        if reason.startswith("missing PDF:"):
            return paper_l0_path(topic_path, bib_key).exists()
        if reason.startswith("L0 shorter than"):
            return False
        if "failed after retry" in reason:
            return paper_l0_path(topic_path, bib_key).exists()

    if op_name == "triage":
        if "missing L0.md" in reason:
            return paper_meta_path(topic_path, bib_key).exists()
        if "validation failed" in reason or "invalid paper_type" in reason:
            return paper_meta_path(topic_path, bib_key).exists()
        return False

    if op_name == "summarize_L3":
        if "missing input" in reason or "empty L3" in reason:
            return paper_l3_path(topic_path, bib_key).exists()
        return False

    if op_name == "extract_L1":
        if "missing" in reason or "schema validation failed" in reason:
            return paper_l1_path(topic_path, bib_key).exists()
        return False

    if op_name == "summarize_L2":
        if "missing L1.json" in reason or "empty L2" in reason:
            return paper_l2_path(topic_path, bib_key).exists()
        return False

    if op_name == "assign_section":
        if "missing input for assignment" in reason:
            return _assignment_contains_bib_key(topic_path, bib_key)
        if "primary_section_path not in outline" in reason:
            return _assignment_contains_bib_key(topic_path, bib_key)
        return False

    return False


def _assignment_contains_bib_key(topic_path: Path, bib_key: str) -> bool:
    path = section_assignments_path(topic_path)
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as handle:
        return any(row.get("bib_key") == bib_key for row in csv.DictReader(handle))


def _assignment_status(topic_path: Path, papers) -> dict[str, object]:
    path = section_assignments_path(topic_path)
    expected = {paper.bib_key for paper in papers}
    if not path.exists():
        return {
            "complete": False,
            "path": str(path),
            "assigned": 0,
            "total": len(expected),
            "missing": sorted(expected),
            "extra": [],
        }

    with path.open("r", encoding="utf-8", newline="") as handle:
        assigned = {row["bib_key"] for row in csv.DictReader(handle) if row.get("bib_key")}

    missing = sorted(expected - assigned)
    extra = sorted(assigned - expected)
    return {
        "complete": len(expected) > 0 and not missing and not extra,
        "path": str(path),
        "assigned": len(assigned & expected),
        "total": len(expected),
        "missing": missing,
        "extra": extra,
    }


def _bundle_status(topic_path: Path) -> dict[str, object]:
    directory = bundles_dir(topic_path)
    if not outline_path(topic_path).exists():
        return {
            "complete": False,
            "path": str(directory),
            "existing": 0,
            "expected": 0,
            "stale": [],
            "missing": [],
        }

    sections = parse_outline(topic_path)
    expected_paths = {
        directory / f"section_{index:02d}_{section.slug}.md"
        for index, section in enumerate(sections, start=1)
    }
    existing_paths = set(directory.glob("*.md")) if directory.exists() else set()
    missing = sorted(path.name for path in expected_paths - existing_paths)
    stale = sorted(path.name for path in existing_paths - expected_paths)
    return {
        "complete": bool(expected_paths) and not missing and not stale,
        "path": str(directory),
        "existing": len(existing_paths & expected_paths),
        "expected": len(expected_paths),
        "stale": stale,
        "missing": missing,
    }


def _suggest_next(rounds: dict[str, object]) -> str:
    for name, info in rounds.items():
        if isinstance(info, dict) and not info.get("complete"):
            return name
    return "done"
