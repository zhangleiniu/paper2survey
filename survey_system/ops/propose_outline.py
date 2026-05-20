from __future__ import annotations

import csv
import time
from pathlib import Path

from survey_system.io.contracts import FailureItem, OpResult
from survey_system.io.kb import read_meta
from survey_system.io.papers import iter_included
from survey_system.llm.client import LLMClient
from survey_system.paths import anchors_csv, outline_candidates_path, paper_l3_path


def propose_outline(
    topic_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    result = OpResult(op_name="propose_outline")
    output_path = outline_candidates_path(topic_path, "v1")
    if output_path.exists() and output_path.stat().st_size > 0 and not force:
        result.skipped.append("outline_candidates_v1")
        result.duration_seconds = time.monotonic() - started
        return result

    if dry_run:
        result.skipped.append("outline_candidates_v1")
        result.duration_seconds = time.monotonic() - started
        return result

    client = llm_client or LLMClient.from_topic(topic_path)
    try:
        corpus_cards = _corpus_cards(topic_path)
    except FileNotFoundError as exc:
        result.failed.append(FailureItem(reason=f"missing input for outline proposal: {exc.filename}"))
        result.duration_seconds = time.monotonic() - started
        return result

    prompt = _prompt_template("propose_outline.txt").replace("{{corpus_cards}}", corpus_cards)
    schema = {
        "type": "object",
        "properties": {"markdown": {"type": "string"}},
        "required": ["markdown"],
        "additionalProperties": False,
    }
    response = client.complete_structured(prompt, schema, model_tier="outline", max_tokens=4096)
    markdown = str(response.get("markdown", "")).strip()
    if not markdown:
        result.failed.append(FailureItem(reason="LLM returned empty outline markdown"))
    else:
        output_path.write_text(markdown + "\n", encoding="utf-8")
        result.processed.append("outline_candidates_v1")
        result.artifacts_written.append(output_path)

    result.duration_seconds = time.monotonic() - started
    return result


def _corpus_cards(topic_path: Path) -> str:
    anchors = _anchor_keys(topic_path)
    lines: list[str] = []
    for paper in iter_included(topic_path):
        meta = read_meta(topic_path, paper.bib_key)
        l3 = paper_l3_path(topic_path, paper.bib_key).read_text(encoding="utf-8").strip()
        anchor_tag = " (ANCHOR)" if paper.bib_key in anchors else ""
        lines.append(
            f"- {paper.bib_key}{anchor_tag}: {paper.title} ({paper.year}, {paper.venue}); "
            f"type={meta.paper_type}; L3={l3}"
        )
    return "\n".join(lines)


def _anchor_keys(topic_path: Path) -> set[str]:
    path = anchors_csv(topic_path)
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["bib_key"] for row in csv.DictReader(handle) if row.get("bib_key")}


def _prompt_template(filename: str) -> str:
    return (Path(__file__).parents[1] / "llm" / "prompts" / filename).read_text(
        encoding="utf-8"
    )
