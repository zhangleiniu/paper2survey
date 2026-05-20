from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from survey_system.config import load_config
from survey_system.io.contracts import FailureItem, OpResult
from survey_system.io.kb import read_meta
from survey_system.io.papers import iter_included
from survey_system.llm.client import LLMClient
from survey_system.paths import anchors_candidates_csv, paper_l3_path


def propose_anchors(
    topic_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    result = OpResult(op_name="propose_anchors")
    output_path = anchors_candidates_csv(topic_path, "v1")
    if output_path.exists() and output_path.stat().st_size > 0 and not force:
        result.skipped.append("anchors_candidates_v1")
        result.duration_seconds = time.monotonic() - started
        return result
    if dry_run:
        result.skipped.append("anchors_candidates_v1")
        result.duration_seconds = time.monotonic() - started
        return result

    client = llm_client or LLMClient.from_topic(topic_path)
    try:
        rows, corpus_cards = _candidate_inputs(topic_path)
    except FileNotFoundError as exc:
        result.failed.append(FailureItem(reason=f"missing input for anchors: {exc.filename}"))
        result.duration_seconds = time.monotonic() - started
        return result

    scores = _score_papers(client, corpus_cards)
    for row in rows:
        score = scores.get(row["bib_key"], {"llm_score": 0, "llm_reason": "No LLM score returned."})
        llm_score = float(score.get("llm_score", 0))
        row["llm_score"] = f"{llm_score:g}"
        row["llm_reason"] = str(score.get("llm_reason", ""))
        row["suggested"] = str(
            row["is_survey"] == "true"
            or (row["venue_tier"] == "1" and llm_score >= 4)
        ).lower()
        row["your_decision"] = ""
        row["role_notes"] = ""

    _write_candidates(output_path, rows)
    result.processed.append("anchors_candidates_v1")
    result.artifacts_written.append(output_path)
    result.duration_seconds = time.monotonic() - started
    return result


def _candidate_inputs(topic_path: Path) -> tuple[list[dict[str, str]], str]:
    config = load_config(topic_path)
    rows: list[dict[str, str]] = []
    cards: list[str] = []
    for paper in iter_included(topic_path):
        meta = read_meta(topic_path, paper.bib_key)
        l3 = paper_l3_path(topic_path, paper.bib_key).read_text(encoding="utf-8").strip()
        venue_tier = config.venue_tiers.get(paper.venue, 3)
        is_survey = meta.paper_type == "survey"
        rows.append(
            {
                "bib_key": paper.bib_key,
                "title": paper.title,
                "year": str(paper.year),
                "venue": paper.venue,
                "venue_tier": str(venue_tier),
                "is_survey": str(is_survey).lower(),
            }
        )
        cards.append(
            f"- {paper.bib_key}: {paper.title} ({paper.year}, {paper.venue}, tier {venue_tier}); "
            f"type={meta.paper_type}; L3={l3}"
        )
    return rows, "\n".join(cards)


def _score_papers(client: LLMClient, corpus_cards: str) -> dict[str, dict[str, Any]]:
    prompt = _prompt_template("propose_anchors.txt").replace("{{corpus_cards}}", corpus_cards)
    schema = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "bib_key": {"type": "string"},
                        "llm_score": {"type": "number"},
                        "llm_reason": {"type": "string"},
                    },
                    "required": ["bib_key", "llm_score", "llm_reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["scores"],
        "additionalProperties": False,
    }
    response = client.complete_structured(prompt, schema, model_tier="outline", max_tokens=4096)
    return {str(item["bib_key"]): item for item in response.get("scores", [])}


def _write_candidates(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "bib_key",
        "title",
        "year",
        "venue",
        "venue_tier",
        "llm_score",
        "llm_reason",
        "is_survey",
        "suggested",
        "your_decision",
        "role_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prompt_template(filename: str) -> str:
    return (Path(__file__).parents[1] / "llm" / "prompts" / filename).read_text(
        encoding="utf-8"
    )
