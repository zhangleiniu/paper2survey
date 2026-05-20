from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from survey_system.config import load_config
from survey_system.io.contracts import FailureItem, Meta, OpResult, PAPER_TYPES, PaperRow
from survey_system.io.kb import extract_abstract_and_intro, read_L0, write_meta
from survey_system.io.papers import get_paper, iter_included
from survey_system.io.review import append_review_item
from survey_system.llm.client import LLMClient
from survey_system.paths import paper_meta_path


def triage(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    config = load_config(topic_path)
    client = llm_client or LLMClient.from_topic(topic_path)
    papers = _select_papers(topic_path, bib_key, limit)
    result = OpResult(op_name="triage")
    schema = Meta.model_json_schema()
    prompt_template = _prompt_template("triage.txt")

    for paper in papers:
        meta_path = paper_meta_path(topic_path, paper.bib_key)
        if meta_path.exists() and meta_path.stat().st_size > 0 and not force:
            result.skipped.append(paper.bib_key)
            continue

        try:
            excerpt = extract_abstract_and_intro(read_L0(topic_path, paper.bib_key))
        except FileNotFoundError:
            reason = "missing L0.md; run round0 first"
            append_review_item(topic_path, paper.bib_key, "triage", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        if dry_run:
            result.skipped.append(paper.bib_key)
            continue

        prompt = _render_template(prompt_template, excerpt)
        response = _complete_with_retry(client, prompt, schema)
        paper_type = response.get("paper_type")

        if paper_type not in PAPER_TYPES:
            reason = f"invalid paper_type after retry: {paper_type!r}"
            partial = _partial_meta(response)
            path = write_meta(topic_path, paper.bib_key, partial)
            append_review_item(topic_path, paper.bib_key, "triage", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            result.artifacts_written.append(path)
            continue

        try:
            meta = Meta.model_validate(response)
        except ValidationError as exc:
            reason = f"meta schema validation failed: {exc}"
            append_review_item(topic_path, paper.bib_key, "triage", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        path = write_meta(topic_path, paper.bib_key, meta)
        result.artifacts_written.append(path)
        result.processed.append(paper.bib_key)

        if meta.paper_type_confidence < config.thresholds.triage_confidence_review_below:
            append_review_item(
                topic_path,
                paper.bib_key,
                "triage",
                f"low confidence: {meta.paper_type_confidence}",
            )

    result.duration_seconds = time.monotonic() - started
    return result


def _select_papers(topic_path: Path, bib_key: str | None, limit: int | None) -> list[PaperRow]:
    if bib_key is not None:
        papers = [get_paper(topic_path, bib_key)]
    else:
        papers = list(iter_included(topic_path))
    return papers[:limit] if limit is not None else papers


def _complete_with_retry(
    client: LLMClient,
    prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    response = client.complete_structured(prompt, schema, model_tier="triage", max_tokens=1024)
    if response.get("paper_type") in PAPER_TYPES:
        return response
    return client.complete_structured(prompt, schema, model_tier="triage", max_tokens=1024)


def _partial_meta(response: dict[str, Any]) -> Meta:
    topics = response.get("topics", [])
    if not isinstance(topics, list):
        topics = []
    return Meta(
        paper_type=None,
        paper_type_confidence=0.0,
        tldr=str(response.get("tldr", "")),
        topics=[str(topic) for topic in topics],
        anchor=bool(response.get("anchor", False)),
    )


def _prompt_template(filename: str) -> str:
    return (Path(__file__).parents[1] / "llm" / "prompts" / filename).read_text(
        encoding="utf-8"
    )


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered
