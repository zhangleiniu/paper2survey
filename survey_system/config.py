from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from survey_system.io.contracts import TopicConfig
from survey_system.paths import config_file


def load_config(topic_path: Path) -> TopicConfig:
    """Load and validate a topic's config.yaml."""
    path = config_file(topic_path)
    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}
    return TopicConfig.model_validate(data)
