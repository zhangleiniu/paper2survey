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
    review_items = _review_count(topic_path)
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
        "review_queue_items": review_items,
        "suggested_next_op": _suggest_next(rounds),
        "rounds": rounds,
        "recent_runs": recent_runs(topic_path),
    }
    if detailed:
        status["review_items"] = _review_rows(topic_path)
    return status


def _count_existing(topic_path: Path, papers, path_func) -> dict[str, object]:
    count = sum(1 for paper in papers if path_func(topic_path, paper.bib_key).exists())
    return {"complete": count == len(papers) and len(papers) > 0, "count": count, "total": len(papers)}


def _review_count(topic_path: Path) -> int:
    return len(_review_rows(topic_path))


def _review_rows(topic_path: Path) -> list[dict[str, str]]:
    path = review_needed_csv(topic_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
