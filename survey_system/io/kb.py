from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from survey_system.io.contracts import Meta
from survey_system.paths import (
    paper_artifacts_dir,
    paper_l0_path,
    paper_l1_path,
    paper_l2_path,
    paper_l3_path,
    paper_meta_path,
)


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


def write_L3(topic_path: Path, bib_key: str, text: str) -> Path:
    path = paper_l3_path(topic_path, bib_key)
    paper_artifacts_dir(topic_path, bib_key).mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def write_L1(topic_path: Path, bib_key: str, l1: BaseModel | dict[str, Any]) -> Path:
    path = paper_l1_path(topic_path, bib_key)
    paper_artifacts_dir(topic_path, bib_key).mkdir(parents=True, exist_ok=True)
    if isinstance(l1, BaseModel):
        payload = l1.model_dump(mode="json", by_alias=True)
    else:
        payload = l1
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_L1(topic_path: Path, bib_key: str) -> dict[str, Any]:
    with paper_l1_path(topic_path, bib_key).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_L2(topic_path: Path, bib_key: str, text: str) -> Path:
    path = paper_l2_path(topic_path, bib_key)
    paper_artifacts_dir(topic_path, bib_key).mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def read_L2(topic_path: Path, bib_key: str) -> str:
    return paper_l2_path(topic_path, bib_key).read_text(encoding="utf-8")


def extract_abstract_and_intro(L0_text: str) -> dict[str, str]:
    sections = _markdown_sections(L0_text)
    abstract = sections.get("abstract", "")
    introduction = sections.get("introduction", "")
    intro_first_para = _first_paragraph(introduction)

    if not abstract and not intro_first_para:
        fallback = L0_text.strip()[:2000]
        return {"abstract": fallback, "intro_first_para": ""}

    return {
        "abstract": abstract.strip()[:2000],
        "intro_first_para": intro_first_para.strip()[:2000],
    }


def _markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip().lower()
            current = title
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _first_paragraph(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return paragraphs[0] if paragraphs else ""
