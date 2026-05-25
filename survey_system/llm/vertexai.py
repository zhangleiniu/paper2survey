from __future__ import annotations

import json
import os
from typing import Any


class VertexAIBackend:
    def __init__(
        self,
        client: Any | None = None,
        project: str | None = None,
        location: str | None = None,
        thinking_budget: int | None = None,
    ) -> None:
        self._client = client
        self._project = project
        self._location = location
        self._thinking_budget = thinking_budget

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
                from google.genai.types import HttpOptions
            except ImportError as exc:
                raise RuntimeError(
                    "google-genai is not installed. Install project dependencies with: uv sync"
                ) from exc

            project = self._project or os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = self._location or os.environ.get("GOOGLE_CLOUD_LOCATION")
            missing = [
                name
                for name, value in {
                    "vertexai.project or GOOGLE_CLOUD_PROJECT": project,
                    "vertexai.location or GOOGLE_CLOUD_LOCATION": location,
                }.items()
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise RuntimeError(
                    f"Vertex AI requires {joined}. Authenticate with "
                    "`gcloud auth application-default login`, then set "
                    "vertexai.project and vertexai.location in config.yaml "
                    "or the matching GOOGLE_CLOUD_* environment variables."
                )

            self._client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
                http_options=HttpOptions(api_version="v1"),
            )
        return self._client

    def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_id: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_json_schema": schema,
            "max_output_tokens": max_tokens,
        }
        if self._thinking_budget is not None:
            config["thinking_config"] = {"thinking_budget": self._thinking_budget}

        response = self.client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config,
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed

        content = getattr(response, "text", None)
        if not content:
            finish_reason = _finish_reason(response)
            detail = f" finish_reason={finish_reason}" if finish_reason else ""
            raise RuntimeError(f"Vertex AI response did not include text.{detail}")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Vertex AI response did not contain valid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Vertex AI response JSON was not an object")
        return result


def _finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    return getattr(candidates[0], "finish_reason", None)
