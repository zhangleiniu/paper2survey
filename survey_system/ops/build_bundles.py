from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from survey_system.io.contracts import FailureItem, OpResult
from survey_system.io.kb import read_L1, read_L2
from survey_system.io.outline import OutlineSection, parse_outline
from survey_system.io.papers import read_papers
from survey_system.io.schemas import load_current_schema
from survey_system.paths import anchors_csv, bundles_dir, section_assignments_path


def build_bundles(
    topic_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> OpResult:
    started = time.monotonic()
    result = OpResult(op_name="build_bundles")
    sections = parse_outline(topic_path)
    assignments_path = section_assignments_path(topic_path, "v1")
    if not assignments_path.exists():
        result.failed.append(FailureItem(reason="missing section_assignments_v1.csv"))
        result.duration_seconds = time.monotonic() - started
        return result

    assignments = _read_assignments(assignments_path)
    papers = {paper.bib_key: paper for paper in read_papers(topic_path)}
    anchors = _anchor_keys(topic_path)
    schema = load_current_schema(topic_path)
    output_dir = bundles_dir(topic_path)

    for index, section in enumerate(sections, start=1):
        output_path = output_dir / f"section_{index:02d}_{section.slug}.md"
        if output_path.exists() and output_path.stat().st_size > 0 and not force:
            result.skipped.append(section.path)
            continue
        if dry_run:
            result.skipped.append(section.path)
            continue

        primary_rows = [row for row in assignments if row["primary_section_path"] == section.path]
        secondary_rows = [
            row
            for row in assignments
            if section.path in _split_secondary(row.get("secondary_section_paths", ""))
        ]
        primary_rows.sort(
            key=lambda row: (
                row["bib_key"] not in anchors,
                papers[row["bib_key"]].year,
                papers[row["bib_key"]].bib_key,
            )
        )

        markdown = _bundle_markdown(
            topic_path=topic_path,
            section=section,
            primary_rows=primary_rows,
            secondary_rows=secondary_rows,
            papers=papers,
            anchors=anchors,
            schema=schema,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        result.processed.append(section.path)
        result.artifacts_written.append(output_path)

    result.duration_seconds = time.monotonic() - started
    return result


def _read_assignments(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_secondary(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _anchor_keys(topic_path: Path) -> set[str]:
    path = anchors_csv(topic_path)
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["bib_key"] for row in csv.DictReader(handle) if row.get("bib_key")}


def _bundle_markdown(
    topic_path: Path,
    section: OutlineSection,
    primary_rows: list[dict[str, str]],
    secondary_rows: list[dict[str, str]],
    papers,
    anchors: set[str],
    schema,
) -> str:
    lines = [f"# {section.path}", ""]
    anchor_rows = [row for row in primary_rows if row["bib_key"] in anchors]
    other_rows = [row for row in primary_rows if row["bib_key"] not in anchors]

    if anchor_rows:
        lines.extend(["## Anchor Papers", ""])
        for row in anchor_rows:
            lines.extend(_paper_block(topic_path, row["bib_key"], papers, schema))

    if other_rows:
        lines.extend(["## Papers", ""])
        for row in other_rows:
            lines.extend(_paper_block(topic_path, row["bib_key"], papers, schema))

    if not primary_rows:
        lines.extend(["_No primary papers assigned._", ""])

    if secondary_rows:
        lines.extend(["## Cross-references", ""])
        for row in secondary_rows:
            paper = papers[row["bib_key"]]
            lines.append(f"- {paper.title} (`{paper.bib_key}`)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _paper_block(topic_path: Path, bib_key: str, papers, schema) -> list[str]:
    paper = papers[bib_key]
    l1 = read_L1(topic_path, bib_key)
    l2 = read_L2(topic_path, bib_key)
    paper_type = l1.get("_paper_type", "")
    bundle_fields = schema.by_type.get(paper_type, {}).get("_bundle_fields", [])
    selected = {
        "universal": l1.get("universal", {}),
        "type_specific": {
            key: l1.get("type_specific", {}).get(key)
            for key in bundle_fields
            if key in l1.get("type_specific", {})
        },
    }
    return [
        f"### {paper.title} (`{paper.bib_key}`)",
        "",
        l2.strip(),
        "",
        "**Key L1 fields**",
        "",
        "```json",
        json.dumps(selected, indent=2),
        "```",
        "",
    ]
