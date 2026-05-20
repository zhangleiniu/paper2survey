from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from survey_system.io.contracts import Meta
from survey_system.paths import paper_artifacts_dir, paper_l0_path, paper_l1_path, paper_meta_path


def read_meta(topic_path: Path, bib_key: str) -> Meta:
    path = paper_meta_path(topic_path, bib_key)
    with path.open("r", encoding="utf-8") as handle:
        return Meta.model_validate(json.load(handle))


def write_meta(topic_path: Path, bib_key: str, meta: Meta) -> Path:
    path = paper_meta_path(topic_path, bib_key)
    paper_artifacts_dir(topic_path, bib_key).mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def read_L0(topic_path: Path, bib_key: str) -> str:
    return paper_l0_path(topic_path, bib_key).read_text(encoding="utf-8")


def write_L1(topic_path: Path, bib_key: str, l1: BaseModel | dict[str, Any]) -> Path:
    path = paper_l1_path(topic_path, bib_key)
    paper_artifacts_dir(topic_path, bib_key).mkdir(parents=True, exist_ok=True)
    if isinstance(l1, BaseModel):
        payload = l1.model_dump(mode="json", by_alias=True)
    else:
        payload = l1
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
