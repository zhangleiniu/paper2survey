from __future__ import annotations

from pathlib import Path

from survey_system.io.contracts import OpResult


def propose_anchors(
    topic_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> OpResult:
    _ = (topic_path, force, dry_run)
    return OpResult.empty("propose_anchors")
