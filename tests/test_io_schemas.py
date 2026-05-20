from pathlib import Path

import pytest

from survey_system.io.schemas import (
    SchemaValidationError,
    current_schema_version,
    load_current_schema,
    schema_for_paper_type,
    validate_json_schema,
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
