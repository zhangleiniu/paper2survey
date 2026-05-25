from pathlib import Path

import pytest

from survey_system.io.schemas import (
    SchemaValidationError,
    current_schema_version,
    diff_schema_payloads,
    load_current_schema,
    load_schema_payload,
    next_schema_version,
    promote_schema,
    schema_for_paper_type,
    inspect_schema_payload,
    validate_json_schema,
    write_schema_candidate,
)


FIXTURE = Path("tests/fixtures/mini_topic")


def test_load_current_schema() -> None:
    schema = load_current_schema(FIXTURE)

    assert current_schema_version(FIXTURE) == "v1"
    assert schema.version == "v1"
    assert "survey" in schema.by_type


def test_schema_for_paper_type_validates_l1_payload() -> None:
    schema = schema_for_paper_type(FIXTURE, "survey")
    payload = {
        "_schema_version": "v1",
        "_paper_type": "survey",
        "universal": {
            "problem": "Too many widget papers.",
            "contributions": ["Organizes widgets"],
            "datasets": [],
            "limitations": ["Synthetic fixture"],
        },
        "type_specific": {
            "scope": "Widget methods",
            "taxonomy": ["survey", "fixture"],
        },
    }

    validate_json_schema(payload, schema)


def test_schema_validation_rejects_missing_required_field() -> None:
    schema = schema_for_paper_type(FIXTURE, "survey")
    payload = {
        "_schema_version": "v1",
        "_paper_type": "survey",
        "universal": {
            "problem": "Too many widget papers.",
            "contributions": [],
            "datasets": [],
            "limitations": [],
        },
        "type_specific": {"scope": "Widget methods"},
    }

    with pytest.raises(SchemaValidationError):
        validate_json_schema(payload, schema)


def test_schema_version_bump_and_promotion(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    __import__("shutil").copytree(FIXTURE, topic)
    payload = load_schema_payload(topic, "v1")
    payload["version"] = "v2"

    path = write_schema_candidate(topic, payload)
    promoted = promote_schema(topic, "v2")

    assert path.name == "schema_v2.json"
    assert promoted.read_text(encoding="utf-8").strip() == "v2"
    assert current_schema_version(topic) == "v2"
    assert load_schema_payload(topic, "v2")["_provenance"]["promoted_at"]


def test_inspect_schema_payload_reports_valid_fixture() -> None:
    payload = load_schema_payload(FIXTURE, "v1")

    inspection = inspect_schema_payload(payload)

    assert inspection["valid"] is True
    assert inspection["issues"] == []
    assert "problem" in inspection["universal_fields"]
    assert "method_idea" in inspection["by_type"]["method"]["fields"]


def test_write_schema_candidate_rejects_empty_universal(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    __import__("shutil").copytree(FIXTURE, topic)
    payload = load_schema_payload(topic, "v1")
    payload["version"] = "v2"
    payload["universal"] = {}

    with pytest.raises(SchemaValidationError, match="universal"):
        write_schema_candidate(topic, payload)


def test_promote_schema_rejects_invalid_candidate(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    __import__("shutil").copytree(FIXTURE, topic)
    payload = load_schema_payload(topic, "v1")
    payload["version"] = "v2"
    payload["by_type"]["method"]["_bundle_fields"] = ["not_a_real_field"]
    (topic / "schemas" / "schema_v2.json").write_text(
        __import__("json").dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(SchemaValidationError, match="_bundle_fields"):
        promote_schema(topic, "v2")


def test_next_schema_version_and_diff(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    __import__("shutil").copytree(FIXTURE, topic)
    old = load_schema_payload(topic, "v1")
    new = load_schema_payload(topic, "v1")
    new["universal"]["properties"]["new_field"] = {"type": "string"}

    assert next_schema_version(topic) == "v2"
    assert diff_schema_payloads(old, new)["universal"]["added"] == ["new_field"]
