from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from survey_system.config import load_config
from survey_system.io.contracts import OpResult
from survey_system.ops import (
    assign_section,
    build_bundles,
    extract,
    parse_pdf,
    propose_anchors,
    propose_outline,
    summarize,
    triage,
)
from survey_system.status import topic_status

app = typer.Typer(help="Survey writing system.")
topic_app = typer.Typer(help="Create and inspect topic workspaces.")
run_app = typer.Typer(help="Run survey operations.")
app.add_typer(topic_app, name="topic")
app.add_typer(run_app, name="run")

TopicOption = Annotated[Path, typer.Option("--topic", "-t", exists=False, file_okay=False)]


def _echo_result(result: OpResult) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


@topic_app.command("init")
def topic_init(topic: TopicOption) -> None:
    topic.mkdir(parents=True, exist_ok=True)
    _echo_result(OpResult.empty("topic.init"))


@topic_app.command("status")
def topic_status_command(topic: TopicOption) -> None:
    typer.echo(json.dumps(topic_status(topic), indent=2, default=str))


@run_app.command("parse-pdf")
def run_parse_pdf(topic: TopicOption) -> None:
    _echo_result(parse_pdf.parse_pdf(topic))


@run_app.command("triage")
def run_triage(topic: TopicOption) -> None:
    _echo_result(triage.triage(topic))


@run_app.command("extract")
def run_extract(topic: TopicOption) -> None:
    _echo_result(extract.extract_l1(topic))


@run_app.command("summarize")
def run_summarize(topic: TopicOption) -> None:
    _echo_result(summarize.summarize(topic))


@run_app.command("propose-anchors")
def run_propose_anchors(topic: TopicOption) -> None:
    _echo_result(propose_anchors.propose_anchors(topic))


@run_app.command("propose-outline")
def run_propose_outline(topic: TopicOption) -> None:
    _echo_result(propose_outline.propose_outline(topic))


@run_app.command("assign-section")
def run_assign_section(topic: TopicOption) -> None:
    _echo_result(assign_section.assign_section(topic))


@run_app.command("build-bundles")
def run_build_bundles(topic: TopicOption) -> None:
    _echo_result(build_bundles.build_bundles(topic))


@run_app.command("noop")
def run_noop(topic: TopicOption) -> None:
    load_config(topic)
    _echo_result(OpResult.empty("noop"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
