from __future__ import annotations

import shutil
from pathlib import Path

from survey_system.io.assignments import inspect_assignments


FIXTURE = Path("tests/fixtures/mini_topic")


def test_inspect_assignments_reports_quality_summary(tmp_path: Path) -> None:
    topic = _topic_with_assignments(tmp_path)

    inspection = inspect_assignments(topic, overloaded_above=1)

    assert inspection["valid"] is True
    assert inspection["assigned"] == 3
    assert inspection["total"] == 3
    assert inspection["secondary_count"] == 1
    assert inspection["section_counts"]["1. Foundations / 1.1 Widget Surveys"] == 2
    assert inspection["overloaded_sections"] == [
        {"section": "1. Foundations / 1.1 Widget Surveys", "count": 2}
    ]
    assert inspection["empty_sections"] == ["2. Systems / 2.1 Tool Workflows"]


def test_inspect_assignments_reports_missing_and_low_confidence(tmp_path: Path) -> None:
    topic = _topic_with_assignments(tmp_path)
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,,0.4,low\n",
        encoding="utf-8",
    )

    inspection = inspect_assignments(topic)

    assert inspection["valid"] is False
    assert inspection["assigned"] == 1
    assert inspection["missing"] == ["lee2023gadgets", "patel2022systems"]
    assert inspection["low_confidence"][0]["bib_key"] == "smith2024widgets"


def _topic_with_assignments(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,2. Systems / 2.1 Tool Workflows,0.9,ok\n"
        "lee2023gadgets,1. Foundations / 1.2 Gadget Benchmarks,,0.8,ok\n"
        "patel2022systems,1. Foundations / 1.1 Widget Surveys,,0.95,ok\n",
        encoding="utf-8",
    )
    return topic
