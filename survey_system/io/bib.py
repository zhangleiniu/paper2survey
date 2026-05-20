from __future__ import annotations

import re
from pathlib import Path

from survey_system.paths import references_bib

_ENTRY_START = re.compile(r"@(?P<entry_type>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.MULTILINE)
_FIELD_START = re.compile(r"(?P<name>[\w-]+)\s*=", re.MULTILINE)


def parse_bib_entries(topic_path: Path) -> dict[str, dict[str, str]]:
    text = references_bib(topic_path).read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}

    starts = list(_ENTRY_START.finditer(text))
    for index, match in enumerate(starts):
        body_start = match.end()
        body_end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        raw_body = text[body_start:body_end].rsplit("}", 1)[0]
        entry = {
            "entry_type": match.group("entry_type").lower(),
            "bib_key": match.group("key").strip(),
        }
        entry.update(_parse_fields(raw_body))
        entries[entry["bib_key"]] = entry

    return entries


def _parse_fields(raw_body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    matches = list(_FIELD_START.finditer(raw_body))
    for index, match in enumerate(matches):
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_body)
        raw_value = raw_body[value_start:value_end].strip().rstrip(",").strip()
        fields[match.group("name").lower()] = _clean_bib_value(raw_value)
    return fields


def _clean_bib_value(value: str) -> str:
    if len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        value = value[1:-1]
    elif len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return " ".join(value.split())


def get_bib_entry(topic_path: Path, bib_key: str) -> dict[str, str]:
    entries = parse_bib_entries(topic_path)
    try:
        return entries[bib_key]
    except KeyError as exc:
        raise KeyError(f"BibTeX entry not found: {bib_key}") from exc
