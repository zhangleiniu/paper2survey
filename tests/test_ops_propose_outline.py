from __future__ import annotations

import shutil
from pathlib import Path

from survey_system.io.contracts import Meta
from survey_system.io.kb import write_L3, write_meta
from survey_system.ops.propose_outline import propose_outline


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeOutlineClient:
    def __init__(self) -> None:
        self.prompt = ""

    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        self.prompt = prompt
        return {
            "markdown": "# Candidate A\n\n## 1. Foundations\n\n### 1.1 Widget Surveys\n\n## Trade-offs\n\nBalanced.\n\n# Candidate B\n\n## 1. Systems\n\n### 1.1 Tool Workflows\n\n## Trade-offs\n\nFocused."
        }


def test_propose_outline_writes_candidates_and_tags_anchors(tmp_path: Path) -> None:
    topic = _topic_with_round1(tmp_path)
    (topic / "anchors.csv").write_text("bib_key,role_notes\nsmith2024widgets,core\n", encoding="utf-8")
    client = FakeOutlineClient()

    result = propose_outline(topic, llm_client=client)

    assert result.processed == ["outline_candidates_v1"]
    text = (topic / "outline_candidates_v1.md").read_text(encoding="utf-8")
    assert text.count("# Candidate") == 2
    assert text.count("Trade-offs") == 2
    assert "smith2024widgets (ANCHOR)" in client.prompt


def test_propose_outline_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_round1(tmp_path)
    client = FakeOutlineClient()

    propose_outline(topic, llm_client=client)
    second = propose_outline(topic, llm_client=FakeOutlineClient())

    assert second.processed == []
    assert second.skipped == ["outline_candidates_v1"]


def _topic_with_round1(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    for bib_key in ["smith2024widgets", "lee2023gadgets", "patel2022systems"]:
        write_meta(topic, bib_key, Meta(paper_type="survey", paper_type_confidence=0.9))
        write_L3(topic, bib_key, f"{bib_key} is a compact fixture card for outline proposal testing.")
    return topic
