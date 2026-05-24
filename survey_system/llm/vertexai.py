from __future__ import annotations

import json
import os
from typing import Any


class VertexAIBackend:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

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

            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION")
            missing = [
                name
                for name, value in {
                    "GOOGLE_CLOUD_PROJECT": project,
                    "GOOGLE_CLOUD_LOCATION": location,
                }.items()
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise RuntimeError(
                    f"Vertex AI requires {joined}. Authenticate with "
                    "`gcloud auth application-default login`, then set "
                    "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION."
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
        response = self.client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": schema,
                "max_output_tokens": max_tokens,
            },
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed

        content = getattr(response, "text", None) or "{}"
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Vertex AI response did not contain valid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Vertex AI response JSON was not an object")
        return result
