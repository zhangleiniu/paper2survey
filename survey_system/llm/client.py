from __future__ import annotations

from typing import Any


class LLMClient:
    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_tier: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        _ = (prompt, schema, model_tier, max_tokens)
        return {}
