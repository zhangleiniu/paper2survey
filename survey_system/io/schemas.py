from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from survey_system.io.contracts import PAPER_TYPES
from survey_system.paths import schemas_dir


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TopicSchema:
    version: str
    universal: dict[str, Any]
    by_type: dict[str, dict[str, Any]]


def current_schema_version(topic_path: Path) -> str:
    return (schemas_dir(topic_path) / "current.txt").read_text(encoding="utf-8").strip()


def load_current_schema(topic_path: Path) -> TopicSchema:
    version = current_schema_version(topic_path)
    path = schemas_dir(topic_path) / f"schema_{version}.json"
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    schema = TopicSchema(
        version=str(payload["version"]),
        universal=dict(payload["universal"]),
        by_type=dict(payload["by_type"]),
    )
    missing = set(PAPER_TYPES) - set(schema.by_type)
    if missing:
        raise SchemaValidationError(f"schema is missing paper types: {sorted(missing)}")
    return schema


def schema_for_paper_type(topic_path: Path, paper_type: str) -> dict[str, Any]:
    schema = load_current_schema(topic_path)
    if paper_type not in schema.by_type:
        raise SchemaValidationError(f"schema has no sub-schema for paper_type={paper_type!r}")
    return assemble_l1_schema(schema, paper_type)


def assemble_l1_schema(schema: TopicSchema, paper_type: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "_schema_version": {"type": "string", "const": schema.version},
            "_paper_type": {"type": "string", "const": paper_type},
            "universal": schema.universal,
            "type_specific": schema.by_type[paper_type],
        },
        "required": ["_schema_version", "_paper_type", "universal", "type_specific"],
        "additionalProperties": False,
    }


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise SchemaValidationError(f"{path} expected {expected_type}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path} expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path} expected one of {schema['enum']!r}, got {value!r}")

    if expected_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise SchemaValidationError(f"{path} has unexpected properties: {sorted(extra)}")
        for key, subschema in properties.items():
            if key in value:
                validate_json_schema(value[key], subschema, f"{path}.{key}")

    if expected_type == "array":
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, f"{path}[{index}]")


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    return True
