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
