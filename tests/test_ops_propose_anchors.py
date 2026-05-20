from __future__ import annotations

import csv
import shutil
from pathlib import Path

from survey_system.io.contracts import Meta
from survey_system.io.kb import write_L3, write_meta
from survey_system.ops.propose_anchors import propose_anchors


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeAnchorClient:
    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        return {
            "scores": [
                {
                    "bib_key": "smith2024widgets",
                    "llm_score": 5,
                    "llm_reason": "Broad survey.",
                },
                {
                    "bib_key": "lee2023gadgets",
                    "llm_score": 4,
                    "llm_reason": "Strong benchmark.",
                },
                {
                    "bib_key": "patel2022systems",
                    "llm_score": 2,
                    "llm_reason": "Narrow system.",
                },
            ]
        }


def test_propose_anchors_writes_candidate_csv(tmp_path: Path) -> None:
    topic = _topic_with_round1(tmp_path)

    result = propose_anchors(topic, llm_client=FakeAnchorClient())

    assert result.processed == ["anchors_candidates_v1"]
    with (topic / "anchors_candidates_v1.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bib_key"] == "smith2024widgets"
    assert rows[0]["venue_tier"] == "1"
    assert rows[0]["is_survey"] == "true"
    assert rows[0]["suggested"] == "true"
    assert rows[1]["suggested"] == "false"
    assert rows[0]["your_decision"] == ""


def test_propose_anchors_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_round1(tmp_path)

    propose_anchors(topic, llm_client=FakeAnchorClient())
    second = propose_anchors(topic, llm_client=FakeAnchorClient())

    assert second.processed == []
    assert second.skipped == ["anchors_candidates_v1"]


def _topic_with_round1(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    types = {
        "smith2024widgets": "survey",
        "lee2023gadgets": "benchmark",
        "patel2022systems": "tool_system",
    }
    for bib_key, paper_type in types.items():
        write_meta(topic, bib_key, Meta(paper_type=paper_type, paper_type_confidence=0.9))
        write_L3(topic, bib_key, f"{bib_key} is a compact fixture card for anchor scoring.")
    return topic
