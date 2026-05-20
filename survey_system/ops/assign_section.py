from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from survey_system.io.contracts import FailureItem, OpResult, PaperRow
from survey_system.io.kb import read_L2, read_meta
from survey_system.io.outline import section_paths
from survey_system.io.papers import get_paper, iter_included
from survey_system.io.review import append_review_item
from survey_system.llm.client import LLMClient
from survey_system.paths import outline_path, section_assignments_path


def assign_section(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    result = OpResult(op_name="assign_section")
    assignment_path = section_assignments_path(topic_path, "v1")
    outline = outline_path(topic_path).read_text(encoding="utf-8")
    valid_sections = section_paths(topic_path)
    existing = _existing_assignments(assignment_path) if assignment_path.exists() and not force else {}
    papers = _select_papers(topic_path, bib_key, limit)
    client = llm_client or LLMClient.from_topic(topic_path)

    if force and assignment_path.exists() and not dry_run:
        assignment_path.unlink()

    for paper in papers:
        if paper.bib_key in existing:
            result.skipped.append(paper.bib_key)
            continue

        try:
            meta = read_meta(topic_path, paper.bib_key)
            l2 = read_L2(topic_path, paper.bib_key)
        except FileNotFoundError as exc:
            reason = f"missing input for assignment: {exc.filename}"
            append_review_item(topic_path, paper.bib_key, "assign_section", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        if dry_run:
            result.skipped.append(paper.bib_key)
            continue

        prompt = _render_template(
            _prompt_template("assign_section.txt"),
            {
                "section_paths": "\n".join(f"- {section}" for section in valid_sections),
                "meta": json.dumps(meta.model_dump(mode="json"), indent=2),
                "l2": l2,
                "outline": outline,
            },
        )
        schema = {
            "type": "object",
            "properties": {
                "primary_section_path": {"type": "string"},
                "secondary_section_paths": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": [
                "primary_section_path",
                "secondary_section_paths",
                "confidence",
                "reason",
            ],
            "additionalProperties": False,
        }
        response = client.complete_structured(prompt, schema, model_tier="assign", max_tokens=1024)
        primary = str(response.get("primary_section_path", ""))
        if primary not in valid_sections:
            reason = f"primary_section_path not in outline: {primary}"
            append_review_item(topic_path, paper.bib_key, "assign_section", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        secondary = [
            str(section)
            for section in response.get("secondary_section_paths", [])
            if str(section) in valid_sections and str(section) != primary
        ]
        _append_assignment(
            assignment_path,
            {
                "bib_key": paper.bib_key,
                "primary_section_path": primary,
                "secondary_section_paths": ";".join(secondary),
                "confidence": str(response.get("confidence", 0.0)),
                "reason": str(response.get("reason", "")),
            },
        )
        result.processed.append(paper.bib_key)
        result.artifacts_written.append(assignment_path)

    result.duration_seconds = time.monotonic() - started
    return result


def _select_papers(topic_path: Path, bib_key: str | None, limit: int | None) -> list[PaperRow]:
    if bib_key is not None:
        papers = [get_paper(topic_path, bib_key)]
    else:
        papers = list(iter_included(topic_path))
    return papers[:limit] if limit is not None else papers


def _existing_assignments(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["bib_key"]: row for row in csv.DictReader(handle)}


def _append_assignment(path: Path, row: dict[str, str]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "bib_key",
                "primary_section_path",
                "secondary_section_paths",
                "confidence",
                "reason",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _prompt_template(filename: str) -> str:
    return (Path(__file__).parents[1] / "llm" / "prompts" / filename).read_text(
        encoding="utf-8"
    )


def _render_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered
