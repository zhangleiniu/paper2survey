from __future__ import annotations

from typing import Any


class AnthropicBackend:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic is not installed. Install project dependencies with: pip install -e ."
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_id: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        tool_name = "record_structured_output"
        response = self.client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            tools=[
                {
                    "name": tool_name,
                    "description": "Record the requested structured output.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                tool_input = getattr(block, "input", None)
                if isinstance(tool_input, dict):
                    return tool_input
        raise RuntimeError("Anthropic response did not include forced tool_use output")
