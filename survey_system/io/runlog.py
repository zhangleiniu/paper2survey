from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from survey_system.io.contracts import OpResult
from survey_system.paths import runs_dir


def write_run_log(
    topic_path: Path,
    result: OpResult,
    *,
    cost: float = 0.0,
    notes: str = "",
) -> Path:
    directory = runs_dir(topic_path)
    directory.mkdir(parents=True, exist_ok=True)
    finished_at = datetime.now(UTC)
    started_at = finished_at - timedelta(seconds=result.duration_seconds)
    path = directory / f"{result.op_name}_{finished_at.strftime('%Y%m%d_%H%M%S_%f')}.log"
    payload: dict[str, Any] = {
        "op_name": result.op_name,
        "start_time": started_at.isoformat(),
        "end_time": finished_at.isoformat(),
        "duration_seconds": result.duration_seconds,
        "processed_papers": result.processed,
        "skipped_papers": result.skipped,
        "failed_papers": [item.model_dump(mode="json") for item in result.failed],
        "artifacts_written": [str(path) for path in result.artifacts_written],
        "cost": cost,
        "notes": notes,
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def recent_runs(topic_path: Path, limit: int = 10) -> list[dict[str, Any]]:
    directory = runs_dir(topic_path)
    if not directory.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
            payload = json.loads(first_line)
            payload["path"] = str(path)
            runs.append(payload)
        except (IndexError, json.JSONDecodeError, OSError):
            runs.append({"path": str(path), "op_name": path.stem, "notes": "unparseable log"})
        if len(runs) >= limit:
            break
    return runs
