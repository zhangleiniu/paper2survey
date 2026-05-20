from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
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


def schema_path(topic_path: Path, version: str) -> Path:
    return schemas_dir(topic_path) / f"schema_{version}.json"


def load_schema_payload(topic_path: Path, version: str) -> dict[str, Any]:
    with schema_path(topic_path, version).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_current_schema(topic_path: Path) -> TopicSchema:
    version = current_schema_version(topic_path)
    payload = load_schema_payload(topic_path, version)

    return topic_schema_from_payload(payload)


def topic_schema_from_payload(payload: dict[str, Any]) -> TopicSchema:
    schema = TopicSchema(
        version=str(payload["version"]),
        universal=dict(payload["universal"]),
        by_type=dict(payload["by_type"]),
    )
    missing = set(PAPER_TYPES) - set(schema.by_type)
    if missing:
        raise SchemaValidationError(f"schema is missing paper types: {sorted(missing)}")
    return schema


def next_schema_version(topic_path: Path) -> str:
    current = current_schema_version(topic_path)
    number = _version_number(current)
    return f"v{number + 1}"


def write_schema_candidate(topic_path: Path, payload: dict[str, Any]) -> Path:
    topic_schema_from_payload(payload)
    version = str(payload["version"])
    directory = schemas_dir(topic_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = schema_path(topic_path, version)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def promote_schema(topic_path: Path, version: str) -> Path:
    path = schema_path(topic_path, version)
    if not path.exists():
        raise FileNotFoundError(path)
    payload = load_schema_payload(topic_path, version)
    topic_schema_from_payload(payload)
    provenance = dict(payload.get("_provenance", {}))
    provenance["promoted_at"] = datetime.now(UTC).isoformat()
    payload["_provenance"] = provenance
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    current_path = schemas_dir(topic_path) / "current.txt"
    current_path.write_text(version + "\n", encoding="utf-8")
    return current_path


def diff_schema_payloads(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_universal = set(old.get("universal", {}).get("properties", {}))
    new_universal = set(new.get("universal", {}).get("properties", {}))
    by_type: dict[str, Any] = {}
    for paper_type in sorted(set(old.get("by_type", {})) | set(new.get("by_type", {}))):
        old_fields = set(old.get("by_type", {}).get(paper_type, {}).get("properties", {}))
        new_fields = set(new.get("by_type", {}).get(paper_type, {}).get("properties", {}))
        by_type[paper_type] = {
            "added": sorted(new_fields - old_fields),
            "removed": sorted(old_fields - new_fields),
        }
    return {
        "universal": {
            "added": sorted(new_universal - old_universal),
            "removed": sorted(old_universal - new_universal),
        },
        "by_type": by_type,
    }


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


def _version_number(version: str) -> int:
    if not version.startswith("v") or not version[1:].isdigit():
        raise SchemaValidationError(f"invalid schema version: {version}")
    return int(version[1:])
