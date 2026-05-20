from __future__ import annotations

import csv
from pathlib import Path

from survey_system.io.contracts import PaperRow
from survey_system.paths import papers_csv


def read_papers(topic_path: Path) -> list[PaperRow]:
    path = papers_csv(topic_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [PaperRow.model_validate(row) for row in csv.DictReader(handle)]


def _write_papers(topic_path: Path, papers: list[PaperRow]) -> None:
    path = papers_csv(topic_path)
    fieldnames = list(PaperRow.model_fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for paper in papers:
            writer.writerow(paper.model_dump())


def iter_included(topic_path: Path):
    for paper in read_papers(topic_path):
        if paper.include == "yes":
            yield paper


def get_paper(topic_path: Path, bib_key: str) -> PaperRow:
    for paper in read_papers(topic_path):
        if paper.bib_key == bib_key:
            return paper
    raise KeyError(f"Paper not found: {bib_key}")


def set_include(topic_path: Path, bib_key: str, value: str, reason: str = "") -> PaperRow:
    if value not in {"yes", "no"}:
        raise ValueError("include value must be 'yes' or 'no'")

    papers = read_papers(topic_path)
    updated: PaperRow | None = None
    for index, paper in enumerate(papers):
        if paper.bib_key == bib_key:
            updated = paper.model_copy(
                update={
                    "include": value,
                    "exclusion_reason": reason if value == "no" else "",
                }
            )
            papers[index] = updated
            break

    if updated is None:
        raise KeyError(f"Paper not found: {bib_key}")

    _write_papers(topic_path, papers)
    return updated
