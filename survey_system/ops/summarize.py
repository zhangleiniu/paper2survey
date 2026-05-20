from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from survey_system.io.contracts import FailureItem, OpResult, PaperRow
from survey_system.io.kb import extract_abstract_and_intro, read_L0, read_meta, write_L3
from survey_system.io.papers import get_paper, iter_included
from survey_system.io.review import append_review_item
from survey_system.llm.client import LLMClient
from survey_system.paths import paper_l3_path


def summarize(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> OpResult:
    return summarize_L3(topic_path, bib_key=bib_key, force=force, dry_run=dry_run)


def summarize_L3(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    client = llm_client or LLMClient.from_topic(topic_path)
    papers = _select_papers(topic_path, bib_key, limit)
    result = OpResult(op_name="summarize_L3")
    schema = {
        "type": "object",
        "properties": {"sentence": {"type": "string"}},
        "required": ["sentence"],
        "additionalProperties": False,
    }
    prompt_template = _prompt_template("summarize_l3.txt")

    for paper in papers:
        l3_path = paper_l3_path(topic_path, paper.bib_key)
        if l3_path.exists() and l3_path.stat().st_size > 0 and not force:
            result.skipped.append(paper.bib_key)
            continue

        try:
            meta = read_meta(topic_path, paper.bib_key)
            excerpt = extract_abstract_and_intro(read_L0(topic_path, paper.bib_key))
        except FileNotFoundError as exc:
            reason = f"missing input for L3: {exc.filename}"
            append_review_item(topic_path, paper.bib_key, "summarize_L3", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        if dry_run:
            result.skipped.append(paper.bib_key)
            continue

        prompt = _render_template(
            prompt_template,
            {
                **excerpt,
                "meta": json.dumps(meta.model_dump(mode="json"), indent=2),
            },
        )
        response = client.complete_structured(
            prompt,
            schema,
            model_tier="summarize",
            max_tokens=256,
        )
        sentence = str(response.get("sentence", "")).strip()
        if not sentence:
            reason = "LLM returned empty L3 sentence"
            append_review_item(topic_path, paper.bib_key, "summarize_L3", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            continue

        path = write_L3(topic_path, paper.bib_key, sentence)
        result.artifacts_written.append(path)
        result.processed.append(paper.bib_key)

    result.duration_seconds = time.monotonic() - started
    return result


def _select_papers(topic_path: Path, bib_key: str | None, limit: int | None) -> list[PaperRow]:
    if bib_key is not None:
        papers = [get_paper(topic_path, bib_key)]
    else:
        papers = list(iter_included(topic_path))
    return papers[:limit] if limit is not None else papers


def _prompt_template(filename: str) -> str:
    return (Path(__file__).parents[1] / "llm" / "prompts" / filename).read_text(
        encoding="utf-8"
    )


def _render_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered
