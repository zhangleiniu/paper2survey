from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from survey_system.paths import outline_path


@dataclass(frozen=True)
class OutlineSection:
    title: str
    path: str
    slug: str
    level: int


def parse_outline(topic_path: Path) -> list[OutlineSection]:
    return parse_outline_text(outline_path(topic_path).read_text(encoding="utf-8"))


def parse_outline_text(markdown: str) -> list[OutlineSection]:
    sections: list[OutlineSection] = []
    current_h2: str | None = None
    h2_has_h3 = False

    for line in markdown.splitlines():
        match = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()
        if title.lower() == "trade-offs":
            continue

        if level == 2:
            if current_h2 is not None and not h2_has_h3:
                sections.append(_section(current_h2, 2))
            current_h2 = title
            h2_has_h3 = False
        elif level == 3:
            if current_h2 is None:
                sections.append(_section(title, 3))
            else:
                h2_has_h3 = True
                sections.append(_section(f"{current_h2} / {title}", 3))

    if current_h2 is not None and not h2_has_h3:
        sections.append(_section(current_h2, 2))

    return sections


def section_paths(topic_path: Path) -> list[str]:
    return [section.path for section in parse_outline(topic_path)]


def slugify_section_path(section_path: str) -> str:
    slug = section_path.replace("/", " ")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").lower()
    return slug or "section"


def _section(path: str, level: int) -> OutlineSection:
    return OutlineSection(
        title=path.split("/")[-1].strip(),
        path=path,
        slug=slugify_section_path(path),
        level=level,
    )
