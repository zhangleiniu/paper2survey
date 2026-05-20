from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from survey_system.cli import app
from survey_system.io.contracts import Meta
from survey_system.io.kb import write_meta
from survey_system.ops.summarize import summarize_L3
from tests.test_ops_triage import L0_TEXT


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeLLMClient:
    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        return {
            "sentence": "This fixture paper contributes a compact example for testing Round 1 corpus reconnaissance behavior in small surveys."
        }


def test_summarize_l3_writes_cards(tmp_path: Path) -> None:
    topic = _topic_with_meta_and_l0(tmp_path)

    result = summarize_L3(topic, llm_client=FakeLLMClient())

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    text = (topic / "papers" / "smith2024widgets" / "L3.txt").read_text(encoding="utf-8")
    assert 15 <= len(text.split()) <= 35


def test_summarize_l3_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_meta_and_l0(tmp_path)

    summarize_L3(topic, llm_client=FakeLLMClient())
    second = summarize_L3(topic, llm_client=FakeLLMClient())

    assert second.processed == []
    assert second.skipped == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]


def test_round1_cli_with_mocked_client(tmp_path: Path, monkeypatch) -> None:
    topic = _topic_with_l0_only(tmp_path)

    class Round1Client:
        @classmethod
        def from_topic(cls, topic_path):
            return cls()

        def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
            if model_tier == "triage":
                return {
                    "paper_type": "survey",
                    "paper_type_confidence": 0.9,
                    "tldr": "A mocked Round 1 triage result.",
                    "topics": ["round1"],
                    "anchor": False,
                }
            return {
                "sentence": "This mocked card summarizes a fixture paper for Round 1 reconnaissance testing."
            }

    monkeypatch.setattr("survey_system.cli.LLMClient", Round1Client)

    first = CliRunner().invoke(app, ["run", "round1", "--topic", str(topic)])
    second = CliRunner().invoke(app, ["run", "round1", "--topic", str(topic)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert '"processed": []' in second.output
    assert "smith2024widgets" in second.output


def _topic_with_meta_and_l0(tmp_path: Path) -> Path:
    topic = _topic_with_l0_only(tmp_path)
    for bib_key in L0_TEXT:
        write_meta(
            topic,
            bib_key,
            Meta(
                paper_type="survey",
                paper_type_confidence=0.9,
                tldr="A fixture paper.",
                topics=["fixtures"],
            ),
        )
    return topic


def _topic_with_l0_only(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    for bib_key, text in L0_TEXT.items():
        l0_path = topic / "papers" / bib_key / "L0.md"
        l0_path.parent.mkdir(parents=True, exist_ok=True)
        l0_path.write_text(text, encoding="utf-8")
    return topic
