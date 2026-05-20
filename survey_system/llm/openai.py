from __future__ import annotations

import json
from typing import Any


class OpenAIBackend:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai is not installed") from exc
            self._client = OpenAI()
        return self._client

    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_id: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
