from __future__ import annotations

from pathlib import Path

from survey_system.config import load_config
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
        "round6_assignments": {
            "complete": section_assignments_path(topic_path).exists(),
            "path": str(section_assignments_path(topic_path)),
        },
        "round6_bundles": {
            "complete": bundles_dir(topic_path).exists() and any(bundles_dir(topic_path).glob("*.md")),
            "path": str(bundles_dir(topic_path)),
        },
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
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _suggest_next(rounds: dict[str, object]) -> str:
    for name, info in rounds.items():
        if isinstance(info, dict) and not info.get("complete"):
            return name
    return "done"
