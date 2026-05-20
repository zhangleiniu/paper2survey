from __future__ import annotations

from pathlib import Path
from typing import Any

from survey_system.config import load_config
from survey_system.io.contracts import TopicConfig
from survey_system.llm.anthropic import AnthropicBackend


class StructuredBackend:
    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_id: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        raise NotImplementedError


class LLMClient:
    def __init__(
        self,
        config: TopicConfig,
        backend: StructuredBackend | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or AnthropicBackend()

    @classmethod
    def from_topic(cls, topic_path: Path, backend: StructuredBackend | None = None) -> "LLMClient":
        return cls(load_config(topic_path), backend=backend)

    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_tier: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        model_id = self._model_id(model_tier)
        return self.backend.complete_structured(
            prompt=prompt,
            schema=schema,
            model_id=model_id,
            max_tokens=max_tokens,
        )

    def _model_id(self, model_tier: str) -> str:
        configured = getattr(self.config.models, model_tier, None)
        if configured:
            return configured
        default_tiers = {
            "triage": "cheap",
            "summarize": "cheap",
            "assign": "cheap",
            "extract": "capable",
            "schema_design": "capable",
            "outline": "capable",
        }
        if model_tier in default_tiers:
            return getattr(self.config.models, default_tiers[model_tier])
        if model_tier in {"cheap", "capable"}:
            return getattr(self.config.models, model_tier)
        raise KeyError(f"Unknown model tier: {model_tier}")
