from __future__ import annotations

from pathlib import Path

from survey_system.config import load_config


def topic_status(topic_path: Path) -> dict[str, object]:
    config = load_config(topic_path)
    return {
        "topic_name": config.topic_name,
        "current_round": 0,
        "suggested_next_op": "parse-pdf",
        "review_queue_items": 0,
        "last_runs": {},
    }
