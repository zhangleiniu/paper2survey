from __future__ import annotations

from pathlib import Path

from survey_system.io.contracts import OpResult


def parse_pdf(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> OpResult:
    _ = (topic_path, bib_key, force, dry_run)
    return OpResult.empty("parse_pdf")
