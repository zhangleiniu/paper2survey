from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from survey_system.io.contracts import FailureItem, OpResult, PaperRow
from survey_system.io.kb import read_L0, read_meta, write_L1
from survey_system.io.papers import get_paper, iter_included
from survey_system.io.review import append_review_item
from survey_system.io.schemas import (
    SchemaValidationError,
    load_current_schema,
    schema_for_paper_type,
    validate_json_schema,
)
from survey_system.llm.client import LLMClient
from survey_system.paths import paper_l1_path


MAX_L0_CHARS = 400_000


def extract_L1(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    llm_client: LLMClient | None = None,
    workers: int = 1,
) -> OpResult:
    _ = workers
    started = time.monotonic()
    client = llm_client or LLMClient.from_topic(topic_path)
    topic_schema = load_current_schema(topic_path)
    papers = _select_papers(topic_path, bib_key, limit)
    result = OpResult(op_name="extract_L1")

    for paper in papers:
        l1_path = paper_l1_path(topic_path, paper.bib_key)
        if l1_path.exists() and l1_path.stat().st_size > 0 and not force:
            result.skipped.append(paper.bib_key)
            continue

        try:
            meta = read_meta(topic_path, paper.bib_key)
        except FileNotFoundError:
            reason = "missing meta.json; run round1 first"
            append_review_item(topic_path, paper.bib_key, "extract_L1", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        if meta.paper_type is None:
            reason = "meta.json has no paper_type"
            append_review_item(topic_path, paper.bib_key, "extract_L1", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        try:
            l0_text = read_L0(topic_path, paper.bib_key)
        except FileNotFoundError:
            reason = "missing L0.md; run round0 first"
            append_review_item(topic_path, paper.bib_key, "extract_L1", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        if len(l0_text) > MAX_L0_CHARS:
            l0_text = l0_text[:MAX_L0_CHARS]
            append_review_item(topic_path, paper.bib_key, "extract_L1", "L0 truncated")

        if dry_run:
            result.skipped.append(paper.bib_key)
            continue

        schema = schema_for_paper_type(topic_path, meta.paper_type)
        prompt = _build_prompt(meta.paper_type, topic_schema.version, l0_text)

        try:
            payload = _complete_valid_l1(
                client=client,
                prompt=prompt,
                schema=schema,
                schema_version=topic_schema.version,
                paper_type=meta.paper_type,
            )
        except SchemaValidationError as exc:
            reason = f"L1 schema validation failed after retry: {exc}"
            append_review_item(topic_path, paper.bib_key, "extract_L1", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        path = write_L1(topic_path, paper.bib_key, payload)
        result.artifacts_written.append(path)
        result.processed.append(paper.bib_key)

    result.duration_seconds = time.monotonic() - started
    return result


def extract_l1(*args, **kwargs) -> OpResult:
    return extract_L1(*args, **kwargs)


def _select_papers(topic_path: Path, bib_key: str | None, limit: int | None) -> list[PaperRow]:
    if bib_key is not None:
        papers = [get_paper(topic_path, bib_key)]
    else:
        papers = list(iter_included(topic_path))
    return papers[:limit] if limit is not None else papers


def _complete_valid_l1(
    client: LLMClient,
    prompt: str,
    schema: dict[str, Any],
    schema_version: str,
    paper_type: str,
) -> dict[str, Any]:
    last_error: SchemaValidationError | None = None
    for _ in range(2):
        payload = client.complete_structured(
            prompt,
            schema,
            model_tier="extract",
            max_tokens=4096,
        )
        payload = _with_schema_metadata(payload, schema_version, paper_type)
        try:
            validate_json_schema(payload, schema)
            return payload
        except SchemaValidationError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _with_schema_metadata(
    payload: dict[str, Any],
    schema_version: str,
    paper_type: str,
) -> dict[str, Any]:
    copied = dict(payload)
    copied["_schema_version"] = schema_version
    copied["_paper_type"] = paper_type
    return copied


def _build_prompt(paper_type: str, schema_version: str, l0_text: str) -> str:
    root = Path(__file__).parents[1] / "llm" / "prompts"
    universal = (root / "extract_universal.txt").read_text(encoding="utf-8")
    by_type = (root / "extract_by_type" / f"{paper_type}.txt").read_text(encoding="utf-8")
    prompt = universal.replace("{{paper_type}}", paper_type)
    prompt = prompt.replace("{{schema_version}}", schema_version)
    prompt = prompt.replace("{{l0_text}}", l0_text)
    return prompt + "\n\n" + by_type
