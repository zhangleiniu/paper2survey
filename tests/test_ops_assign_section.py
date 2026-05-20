from __future__ import annotations

import csv
import shutil
from pathlib import Path

from survey_system.io.contracts import Meta
from survey_system.io.kb import write_L2, write_meta
from survey_system.ops.assign_section import assign_section


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeAssignClient:
    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        if '"paper_type": "benchmark"' in prompt:
            primary = "1. Foundations / 1.2 Gadget Benchmarks"
        elif '"paper_type": "tool_system"' in prompt:
            primary = "2. Systems / 2.1 Tool Workflows"
        else:
            primary = "1. Foundations / 1.1 Widget Surveys"
        return {
            "primary_section_path": primary,
            "secondary_section_paths": ["2. Systems / 2.1 Tool Workflows"],
            "confidence": 0.9,
            "reason": "Matches the fixture topic.",
        }


def test_assign_section_writes_valid_rows(tmp_path: Path) -> None:
    topic = _topic_with_l2(tmp_path)

    result = assign_section(topic, llm_client=FakeAssignClient())

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    with (topic / "section_assignments_v1.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert rows[0]["primary_section_path"] == "1. Foundations / 1.1 Widget Surveys"


def test_assign_section_rejects_unknown_primary(tmp_path: Path) -> None:
    topic = _topic_with_l2(tmp_path)

    class BadClient:
        def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
            return {
                "primary_section_path": "No Such Section",
                "secondary_section_paths": [],
                "confidence": 0.1,
                "reason": "bad",
            }

    result = assign_section(topic, bib_key="smith2024widgets", llm_client=BadClient())

    assert result.failed[0].bib_key == "smith2024widgets"
    assert "not in outline" in (topic / "_review_needed.csv").read_text(encoding="utf-8")


def test_assign_section_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_l2(tmp_path)

    assign_section(topic, llm_client=FakeAssignClient())
    second = assign_section(topic, llm_client=FakeAssignClient())

    assert second.processed == []
    assert second.skipped == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]


def _topic_with_l2(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    meta = {
        "smith2024widgets": "survey",
        "lee2023gadgets": "benchmark",
        "patel2022systems": "tool_system",
    }
    for bib_key, paper_type in meta.items():
        write_meta(topic, bib_key, Meta(paper_type=paper_type, paper_type_confidence=0.9))
        write_L2(topic, bib_key, f"This {paper_type} fixture has enough L2 content for assignment.")
    return topic
