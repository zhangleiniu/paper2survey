from pathlib import Path

import pytest

from survey_system.io.bib import get_bib_entry, parse_bib_entries


FIXTURE = Path("tests/fixtures/mini_topic")


def test_parse_bib_entries() -> None:
    entries = parse_bib_entries(FIXTURE)

    assert set(entries) == {
        "smith2024widgets",
        "lee2023gadgets",
        "patel2022systems",
    }
    assert entries["smith2024widgets"]["entry_type"] == "article"
    assert entries["smith2024widgets"]["title"] == "Widget Survey"


def test_get_bib_entry() -> None:
    entry = get_bib_entry(FIXTURE, "patel2022systems")

    assert entry["author"] == "Patel, Dev"
    assert entry["booktitle"] == "Workshop on Examples"


def test_get_bib_entry_missing_key() -> None:
    with pytest.raises(KeyError):
        get_bib_entry(FIXTURE, "missing")
