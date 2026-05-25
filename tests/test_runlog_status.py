from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from survey_system.cli import app
from survey_system.io.runlog import recent_runs
from survey_system.status import topic_status


FIXTURE = Path("tests/fixtures/mini_topic")


def test_cli_run_writes_parseable_jsonl_log(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)

    result = CliRunner().invoke(app, ["run", "noop", "--topic", str(topic)])

    assert result.exit_code == 0
    logs = list((topic / "_runs").glob("noop_*.log"))
    assert logs
    payload = json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])
    assert payload["op_name"] == "noop"
    assert "start_time" in payload
    assert "end_time" in payload
    assert payload["cost"] == 0.0


def test_topic_status_reports_rounds_reviews_and_recent_runs(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "_review_needed.csv").write_text(
        "bib_key,op_name,reason\nsmith2024widgets,triage,check\n",
        encoding="utf-8",
    )
    CliRunner().invoke(app, ["run", "noop", "--topic", str(topic)])

    status = topic_status(topic, detailed=True)

    assert status["review_queue_items"] == 1
    assert "round0" in status["rounds"]
    assert status["recent_runs"]
    assert status["review_items"][0]["bib_key"] == "smith2024widgets"
    assert recent_runs(topic)[0]["op_name"] == "noop"


def test_topic_status_requires_assignment_coverage(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,,0.9,ok\n",
        encoding="utf-8",
    )

    status = topic_status(topic)
    assignment_status = status["rounds"]["round6_assignments"]

    assert assignment_status["complete"] is False
    assert assignment_status["assigned"] == 1
    assert assignment_status["total"] == 3
    assert assignment_status["missing"] == ["lee2023gadgets", "patel2022systems"]


def test_topic_status_reports_stale_bundles(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    bundle_dir = topic / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "section_01_1_foundations_1_1_widget_surveys.md").write_text("ok\n", encoding="utf-8")
    (bundle_dir / "section_02_1_foundations_1_2_gadget_benchmarks.md").write_text("ok\n", encoding="utf-8")
    (bundle_dir / "section_03_2_systems_2_1_tool_workflows.md").write_text("ok\n", encoding="utf-8")
    (bundle_dir / "section_99_old_outline.md").write_text("stale\n", encoding="utf-8")

    status = topic_status(topic)
    bundle_status = status["rounds"]["round6_bundles"]

    assert bundle_status["complete"] is False
    assert bundle_status["existing"] == 3
    assert bundle_status["expected"] == 3
    assert bundle_status["missing"] == []
    assert bundle_status["stale"] == ["section_99_old_outline.md"]
