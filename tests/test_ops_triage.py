from __future__ import annotations

import csv
import shutil
from pathlib import Path

from survey_system.io.contracts import Meta
from survey_system.io.kb import read_meta
from survey_system.ops.triage import triage


FIXTURE = Path("tests/fixtures/mini_topic")
L0_TEXT = {
    "smith2024widgets": "# Abstract\n\nA survey of widget methods.\n\n# Introduction\n\nWidgets need careful organization.",
    "lee2023gadgets": "# Abstract\n\nA benchmark for gadget systems.\n\n# Introduction\n\nGadgets are hard to compare.",
    "patel2022systems": "# Abstract\n\nA tool system for thingamabob workflows.\n\n# Introduction\n\nUsers need practical workflows.",
}


class FakeLLMClient:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.calls = 0

    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        if "a benchmark for gadget" in prompt.lower():
            paper_type = "benchmark"
        elif "a tool system for thingamabob" in prompt.lower():
            paper_type = "tool_system"
        else:
            paper_type = "survey"
        return {
            "paper_type": paper_type,
            "paper_type_confidence": 0.92,
            "tldr": f"A {paper_type} paper about the fixture topic.",
            "topics": ["fixtures"],
            "anchor": paper_type == "survey",
        }


def test_triage_writes_meta_for_mini_topic(tmp_path: Path) -> None:
    topic = _topic_with_l0(tmp_path)

    result = triage(topic, llm_client=FakeLLMClient())

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    for bib_key in result.processed:
        meta = read_meta(topic, bib_key)
        assert isinstance(meta, Meta)
        assert meta.paper_type in {"survey", "benchmark", "tool_system"}


def test_triage_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_l0(tmp_path)

    triage(topic, llm_client=FakeLLMClient())
    second = triage(topic, llm_client=FakeLLMClient())

    assert second.processed == []
    assert second.skipped == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]


def test_triage_workers_parameter_preserves_outputs(tmp_path: Path) -> None:
    topic = _topic_with_l0(tmp_path)

    result = triage(topic, llm_client=FakeLLMClient(), workers=2)

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    assert read_meta(topic, "smith2024widgets").paper_type == "survey"


def test_triage_out_of_enum_writes_partial_meta_and_review(tmp_path: Path) -> None:
    topic = _topic_with_l0(tmp_path)
    client = FakeLLMClient(
        responses=[
            {
                "paper_type": "not_a_type",
                "paper_type_confidence": 0.8,
                "tldr": "Still useful partial text.",
                "topics": ["weird"],
                "anchor": False,
            },
            {
                "paper_type": "still_bad",
                "paper_type_confidence": 0.8,
                "tldr": "Partial text after retry.",
                "topics": ["weird"],
                "anchor": False,
            },
        ]
    )

    result = triage(topic, bib_key="smith2024widgets", llm_client=client)

    assert result.failed[0].bib_key == "smith2024widgets"
    meta = read_meta(topic, "smith2024widgets")
    assert meta.paper_type is None
    assert meta.paper_type_confidence == 0.0
    assert meta.tldr == "Partial text after retry."
    with (topic / "_review_needed.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bib_key"] == "smith2024widgets"
    assert "invalid paper_type" in rows[0]["reason"]


def test_triage_low_confidence_flags_review(tmp_path: Path) -> None:
    topic = _topic_with_l0(tmp_path)
    client = FakeLLMClient(
        responses=[
            {
                "paper_type": "method",
                "paper_type_confidence": 0.2,
                "tldr": "A low confidence classification.",
                "topics": ["widgets"],
                "anchor": False,
            }
        ]
    )

    result = triage(topic, bib_key="smith2024widgets", llm_client=client)

    assert result.processed == ["smith2024widgets"]
    assert "low confidence" in (topic / "_review_needed.csv").read_text(encoding="utf-8")


def _topic_with_l0(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    for bib_key, text in L0_TEXT.items():
        l0_path = topic / "papers" / bib_key / "L0.md"
        l0_path.parent.mkdir(parents=True, exist_ok=True)
        l0_path.write_text(text, encoding="utf-8")
    return topic
