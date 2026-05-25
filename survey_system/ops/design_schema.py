from __future__ import annotations

import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from survey_system.io.contracts import FailureItem, OpResult, PAPER_TYPES
from survey_system.io.kb import read_L0
from survey_system.io.schemas import (
    diff_schema_payloads,
    load_schema_payload,
    next_schema_version,
    promote_schema as promote_schema_version,
    schema_path,
    topic_schema_from_payload,
    write_schema_candidate,
)
from survey_system.llm.client import LLMClient
from survey_system.paths import anchors_csv


MAX_ANCHOR_GROUP_CHARS = 300_000


def design_schema(
    topic_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    llm_client: LLMClient | None = None,
) -> OpResult:
    started = time.monotonic()
    result = OpResult(op_name="design_schema")
    next_version = next_schema_version(topic_path)
    output_path = schema_path(topic_path, next_version)
    if output_path.exists() and output_path.stat().st_size > 0 and not force:
        result.skipped.append(next_version)
        result.duration_seconds = time.monotonic() - started
        return result
    if dry_run:
        result.skipped.append(next_version)
        result.duration_seconds = time.monotonic() - started
        return result

    try:
        anchor_keys = _anchor_keys(topic_path)
        prior_version = _current_version(topic_path)
        prior_schema = load_schema_payload(topic_path, prior_version)
        anchor_l0 = _anchor_l0_groups(topic_path, anchor_keys)
    except FileNotFoundError as exc:
        result.failed.append(FailureItem(reason=f"missing schema design input: {exc.filename}"))
        result.duration_seconds = time.monotonic() - started
        return result

    if not anchor_keys:
        result.failed.append(FailureItem(reason="anchors.csv has no anchors"))
        result.duration_seconds = time.monotonic() - started
        return result

    client = llm_client or LLMClient.from_topic(topic_path)
    response = client.complete_structured(
        _prompt(next_version, prior_schema, anchor_l0),
        _schema_design_output_schema(),
        model_tier="schema_design",
        max_tokens=8192,
    )
    candidate = _candidate_payload(
        response=response,
        next_version=next_version,
        prior_schema=prior_schema,
        anchor_keys=anchor_keys,
    )
    try:
        topic_schema_from_payload(candidate)
    except Exception as exc:
        result.failed.append(FailureItem(reason=f"candidate schema invalid: {exc}"))
        result.duration_seconds = time.monotonic() - started
        return result

    try:
        path = write_schema_candidate(topic_path, candidate)
    except Exception as exc:
        result.failed.append(FailureItem(reason=f"candidate schema invalid: {exc}"))
        result.duration_seconds = time.monotonic() - started
        return result

    result.processed.append(next_version)
    result.artifacts_written.append(path)
    result.duration_seconds = time.monotonic() - started
    return result


def _anchor_keys(topic_path: Path) -> list[str]:
    with anchors_csv(topic_path).open("r", encoding="utf-8", newline="") as handle:
        return [row["bib_key"] for row in csv.DictReader(handle) if row.get("bib_key")]


def _current_version(topic_path: Path) -> str:
    from survey_system.io.schemas import current_schema_version

    return current_schema_version(topic_path)


def _anchor_l0_groups(topic_path: Path, anchor_keys: list[str]) -> str:
    groups: list[str] = []
    current = ""
    for bib_key in anchor_keys:
        block = f"\n\n## {bib_key}\n\n{read_L0(topic_path, bib_key)}"
        if current and len(current) + len(block) > MAX_ANCHOR_GROUP_CHARS:
            groups.append(current)
            current = block
        else:
            current += block
    if current:
        groups.append(current)
    return "\n\n--- GROUP BREAK ---\n\n".join(groups)


def _prompt(next_version: str, prior_schema: dict[str, Any], anchor_l0: str) -> str:
    template = (Path(__file__).parents[1] / "llm" / "prompts" / "design_schema.txt").read_text(
        encoding="utf-8"
    )
    return (
        template.replace("{{next_version}}", next_version)
        .replace("{{prior_schema}}", json.dumps(prior_schema, indent=2))
        .replace("{{anchor_l0}}", anchor_l0)
    )


def _schema_design_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "universal": {"type": "object"},
            "by_type": {"type": "object"},
            "_provenance": {"type": "object"},
        },
        "required": ["version", "universal", "by_type"],
        "additionalProperties": True,
    }


def _candidate_payload(
    response: dict[str, Any],
    next_version: str,
    prior_schema: dict[str, Any],
    anchor_keys: list[str],
) -> dict[str, Any]:
    candidate = dict(response)
    candidate["version"] = next_version
    candidate.setdefault("universal", prior_schema["universal"])
    candidate.setdefault("by_type", prior_schema["by_type"])
    for paper_type in PAPER_TYPES:
        candidate["by_type"].setdefault(paper_type, prior_schema["by_type"][paper_type])
    provenance = dict(candidate.get("_provenance", {}))
    provenance.update(
        {
            "based_on_anchors": anchor_keys,
            "promoted_at": "",
            "generated_at": datetime.now(UTC).isoformat(),
            "delta_from_prev": diff_schema_payloads(prior_schema, candidate),
        }
    )
    candidate["_provenance"] = provenance
    return candidate


def promote_schema(topic_path: Path, version: str) -> Path:
    return promote_schema_version(topic_path, version)
