from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from survey_system.cli import app


FIXTURE = Path("tests/fixtures/mini_topic")
runner = CliRunner()


def test_topic_validate_success() -> None:
    result = runner.invoke(app, ["topic", "validate", "--topic", str(FIXTURE)])

    assert result.exit_code == 0
    assert "OK:" in result.output


def test_topic_validate_reports_missing_pdf(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "pdfs" / "lee2023gadgets.pdf").unlink()

    result = runner.invoke(app, ["topic", "validate", "--topic", str(topic)])

    assert result.exit_code == 1
    assert "missing PDF for lee2023gadgets" in result.output


def test_topic_inspect_schema_reports_fields() -> None:
    result = runner.invoke(app, ["topic", "inspect-schema", "--topic", str(FIXTURE)])

    assert result.exit_code == 0
    assert "Schema: v1" in result.output
    assert "Valid: true" in result.output
    assert "problem" in result.output
