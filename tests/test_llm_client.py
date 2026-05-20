from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from survey_system.config import load_config
from survey_system.io.contracts import Meta
from survey_system.llm.anthropic import AnthropicBackend
from survey_system.llm.client import LLMClient


class RecordingBackend:
    def __init__(self) -> None:
        self.model_id: str | None = None

    def complete_structured(self, prompt, schema, model_id, max_tokens=4096):
        self.model_id = model_id
        return {"ok": True}


def test_llm_client_maps_model_tier_from_config() -> None:
    backend = RecordingBackend()
    client = LLMClient(load_config(__import__("pathlib").Path("tests/fixtures/mini_topic")), backend)

    assert client.complete_structured("prompt", {}, "triage") == {"ok": True}
    assert backend.model_id == "placeholder-cheap"


def test_anthropic_backend_returns_forced_tool_input() -> None:
    tool_input = {
        "paper_type": "survey",
        "paper_type_confidence": 0.9,
        "tldr": "A concise survey.",
        "topics": ["widgets"],
        "anchor": False,
    }
    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="ignored"),
            SimpleNamespace(type="tool_use", name="record_structured_output", input=tool_input),
        ]
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: fake_response)
    )

    result = AnthropicBackend(fake_client).complete_structured(
        "prompt",
        Meta.model_json_schema(),
        "fake-model",
    )

    assert Meta.model_validate(result).paper_type == "survey"


@pytest.mark.live
def test_live_anthropic_triage_smoke() -> None:
    if os.environ.get("RUN_LLM_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("set RUN_LLM_LIVE=1 and ANTHROPIC_API_KEY to run live LLM smoke test")

    config = load_config(__import__("pathlib").Path("tests/fixtures/mini_topic"))
    client = LLMClient(config)
    result = client.complete_structured(
        "Classify this paper excerpt: Abstract: A survey of widget methods.",
        Meta.model_json_schema(),
        "triage",
        max_tokens=512,
    )

    meta = Meta.model_validate(result)
    assert meta.paper_type is not None
    assert meta.tldr
