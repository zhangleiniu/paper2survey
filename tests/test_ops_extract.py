from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from survey_system.cli import app
from survey_system.io.contracts import Meta
from survey_system.io.kb import read_L1, write_meta
from survey_system.io.schemas import schema_for_paper_type, validate_json_schema
from survey_system.ops.extract import extract_L1


FIXTURE = Path("tests/fixtures/mini_topic")
L0_TEXT = {
    "smith2024widgets": "# Widget Survey\n\nThis paper surveys widget methods.",
    "lee2023gadgets": "# Gadget Benchmarks\n\nThis paper benchmarks gadget systems.",
    "patel2022systems": "# Tool System\n\nThis paper presents a tool system.",
}


class FakeExtractClient:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.calls = 0

    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        if "benchmark" in prompt.lower():
            return _benchmark_l1()
        if "tool_system" in prompt.lower():
            return _tool_system_l1()
        return _survey_l1()


def test_extract_l1_writes_schema_valid_output(tmp_path: Path) -> None:
    topic = _topic_with_inputs(tmp_path)

    result = extract_L1(topic, llm_client=FakeExtractClient())

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    l1 = read_L1(topic, "smith2024widgets")
    assert l1["_schema_version"] == "v1"
    validate_json_schema(l1, schema_for_paper_type(topic, "survey"))


def test_extract_l1_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_inputs(tmp_path)

    extract_L1(topic, llm_client=FakeExtractClient())
    second = extract_L1(topic, llm_client=FakeExtractClient())

    assert second.processed == []
    assert second.skipped == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]


def test_extract_l1_retries_validation_failure(tmp_path: Path) -> None:
    topic = _topic_with_inputs(tmp_path)
    client = FakeExtractClient(responses=[{"universal": {}, "type_specific": {}}, _survey_l1()])

    result = extract_L1(topic, bib_key="smith2024widgets", llm_client=client)

    assert result.processed == ["smith2024widgets"]
    assert client.calls == 2


def test_extract_l1_logs_after_second_validation_failure(tmp_path: Path) -> None:
    topic = _topic_with_inputs(tmp_path)
    client = FakeExtractClient(
        responses=[
            {"universal": {}, "type_specific": {}},
            {"universal": {}, "type_specific": {}},
        ]
    )

    result = extract_L1(topic, bib_key="smith2024widgets", llm_client=client)

    assert result.failed[0].bib_key == "smith2024widgets"
    assert not (topic / "papers" / "smith2024widgets" / "L1.json").exists()
    assert "schema validation failed" in (topic / "_review_needed.csv").read_text(encoding="utf-8")


def test_extract_l1_fails_if_meta_missing(tmp_path: Path) -> None:
    topic = _topic_with_l0_only(tmp_path)

    result = extract_L1(topic, bib_key="smith2024widgets", llm_client=FakeExtractClient())

    assert result.failed[0].bib_key == "smith2024widgets"
    assert "missing meta.json" in result.failed[0].reason
    assert not (topic / "papers" / "smith2024widgets" / "L1.json").exists()


def test_round4_cli_with_mocked_client_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    topic = _topic_with_inputs(tmp_path)

    class Round4Client:
        @classmethod
        def from_topic(cls, topic_path):
            return cls()

        def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
            if model_tier == "extract":
                if "benchmark" in prompt.lower():
                    return _benchmark_l1()
                if "tool_system" in prompt.lower():
                    return _tool_system_l1()
                return _survey_l1()
            return {"narrative": _l2_text()}

    monkeypatch.setattr("survey_system.cli.LLMClient", Round4Client)

    first = CliRunner().invoke(app, ["run", "round4", "--topic", str(topic)])
    second = CliRunner().invoke(app, ["run", "round4", "--topic", str(topic)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert '"processed": []' in second.output
    assert "smith2024widgets" in second.output


def _topic_with_inputs(tmp_path: Path) -> Path:
    topic = _topic_with_l0_only(tmp_path)
    write_meta(topic, "smith2024widgets", Meta(paper_type="survey", paper_type_confidence=0.9))
    write_meta(topic, "lee2023gadgets", Meta(paper_type="benchmark", paper_type_confidence=0.9))
    write_meta(topic, "patel2022systems", Meta(paper_type="tool_system", paper_type_confidence=0.9))
    return topic


def _topic_with_l0_only(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    for bib_key, text in L0_TEXT.items():
        path = topic / "papers" / bib_key / "L0.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return topic


def _survey_l1() -> dict:
    return {
        "universal": {
            "problem": "Widget papers need organization.",
            "contributions": ["Surveys widget methods"],
            "datasets": [],
            "limitations": ["Fixture only"],
        },
        "type_specific": {
            "scope": "Widget methods",
            "taxonomy": ["methods", "benchmarks"],
        },
    }


def _benchmark_l1() -> dict:
    return {
        "universal": {
            "problem": "Gadgets are hard to compare.",
            "contributions": ["Defines a benchmark"],
            "datasets": ["FakeSet"],
            "limitations": ["Synthetic fixture"],
        },
        "type_specific": {
            "benchmark_goal": "Compare gadget systems",
            "metrics": ["accuracy"],
        },
    }


def _tool_system_l1() -> dict:
    return {
        "universal": {
            "problem": "Thingamabob workflows need tools.",
            "contributions": ["Builds a tool system"],
            "datasets": [],
            "limitations": ["Small fixture"],
        },
        "type_specific": {
            "system_goal": "Support workflows",
            "interface_or_workflow": "Command workflow",
        },
    }


def _l2_text() -> str:
    sentence = (
        "This fixture paper is summarized as a narrative L2 artifact that captures the problem, "
        "the central contribution, the evidence represented by structured fields, and the limitations."
    )
    return " ".join([sentence] * 7)
