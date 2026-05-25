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


def inspect_outline(topic_path: Path) -> dict[str, object]:
    path = outline_path(topic_path)
    if not path.exists():
        return {
            "valid": False,
            "issues": [f"missing outline: {path}"],
            "warnings": [],
            "section_count": 0,
            "sections": [],
            "candidate_headings": [],
        }
    return inspect_outline_text(path.read_text(encoding="utf-8"))


def inspect_outline_text(markdown: str) -> dict[str, object]:
    sections = parse_outline_text(markdown)
    issues: list[str] = []
    warnings: list[str] = []
    candidate_headings = [
        line.strip()
        for line in markdown.splitlines()
        if re.match(r"^#\s+Candidate\b", line.strip(), flags=re.IGNORECASE)
    ]
    if candidate_headings:
        issues.append(
            "outline.md still contains candidate headings; keep only one final outline"
        )
    if len(candidate_headings) > 1:
        issues.append(f"outline.md appears to contain {len(candidate_headings)} candidates")
    if not sections:
        issues.append("outline.md has no parsed H2/H3 sections")
    if re.search(r"^##\s+Trade-offs\s*$", markdown, flags=re.IGNORECASE | re.MULTILINE):
        warnings.append("outline.md still contains a Trade-offs section from proposal output")

    paths = [section.path for section in sections]
    duplicate_paths = sorted({path for path in paths if paths.count(path) > 1})
    if duplicate_paths:
        issues.append(f"outline.md has duplicate section paths: {duplicate_paths}")

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "section_count": len(sections),
        "sections": paths,
        "candidate_headings": candidate_headings,
    }


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
