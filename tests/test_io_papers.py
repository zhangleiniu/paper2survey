from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from survey_system.io.papers import get_paper, iter_included, set_include


FIXTURE = Path("tests/fixtures/mini_topic")


def test_iter_included_returns_yes_rows() -> None:
    papers = list(iter_included(FIXTURE))

    assert [paper.bib_key for paper in papers] == [
        "smith2024widgets",
        "lee2023gadgets",
        "patel2022systems",
    ]


def test_get_paper_by_bib_key() -> None:
    paper = get_paper(FIXTURE, "lee2023gadgets")

    assert paper.title == "Gadget Benchmarks"
    assert paper.year == 2023


def test_set_include_filters_row(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)

    updated = set_include(topic, "lee2023gadgets", "no", "out of scope")

    assert updated.include == "no"
    assert updated.exclusion_reason == "out of scope"
    assert [paper.bib_key for paper in iter_included(topic)] == [
        "smith2024widgets",
        "patel2022systems",
    ]


def test_set_include_rejects_invalid_value(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)

    with pytest.raises(ValueError):
        set_include(topic, "lee2023gadgets", "maybe")
