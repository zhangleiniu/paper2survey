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


def test_topic_inspect_outline_reports_sections() -> None:
    result = runner.invoke(app, ["topic", "inspect-outline", "--topic", str(FIXTURE)])

    assert result.exit_code == 0
    assert "Valid: true" in result.output
    assert "1. Foundations / 1.1 Widget Surveys" in result.output


def test_topic_inspect_assignments_reports_counts(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,,0.9,ok\n"
        "lee2023gadgets,1. Foundations / 1.2 Gadget Benchmarks,,0.9,ok\n"
        "patel2022systems,2. Systems / 2.1 Tool Workflows,,0.9,ok\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["topic", "inspect-assignments", "--topic", str(topic)])

    assert result.exit_code == 0
    assert "Assigned: 3/3" in result.output
    assert "Section counts:" in result.output
