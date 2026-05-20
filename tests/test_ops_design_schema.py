from __future__ import annotations

import shutil
from pathlib import Path

from survey_system.io.schemas import load_schema_payload
from survey_system.ops.design_schema import design_schema


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeSchemaClient:
    def complete_structured(self, prompt, schema, model_tier, max_tokens=4096):
        prior = load_schema_payload(FIXTURE, "v1")
        candidate = {
            "version": "v2",
            "universal": prior["universal"],
            "by_type": prior["by_type"],
            "_provenance": {"delta_from_prev": "mocked candidate"},
        }
        candidate["universal"]["properties"]["anchor_dimension"] = {"type": "string"}
        candidate["universal"]["required"].append("anchor_dimension")
        return candidate


def test_design_schema_writes_next_candidate(tmp_path: Path) -> None:
    topic = _topic_with_anchor_l0(tmp_path)

    result = design_schema(topic, llm_client=FakeSchemaClient())

    assert result.processed == ["v2"]
    payload = load_schema_payload(topic, "v2")
    assert payload["version"] == "v2"
    assert payload["_provenance"]["based_on_anchors"] == ["smith2024widgets"]
    assert "anchor_dimension" in payload["universal"]["properties"]


def test_design_schema_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_anchor_l0(tmp_path)

    design_schema(topic, llm_client=FakeSchemaClient())
    second = design_schema(topic, llm_client=FakeSchemaClient())

    assert second.processed == []
    assert second.skipped == ["v2"]


def test_design_schema_requires_anchors(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)

    result = design_schema(topic, llm_client=FakeSchemaClient())

    assert result.failed
    assert "anchors" in result.failed[0].reason or "missing" in result.failed[0].reason


def _topic_with_anchor_l0(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "anchors.csv").write_text("bib_key,role_notes\nsmith2024widgets,core\n", encoding="utf-8")
    l0_path = topic / "papers" / "smith2024widgets" / "L0.md"
    l0_path.parent.mkdir(parents=True, exist_ok=True)
    l0_path.write_text("# Abstract\n\nAnchor paper for schema design.", encoding="utf-8")
    return topic
