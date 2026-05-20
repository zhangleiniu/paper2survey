from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from survey_system.config import load_config
from survey_system.io.anchors import curate_anchors
from survey_system.io.bib import parse_bib_entries
from survey_system.io.contracts import OpResult
from survey_system.io.papers import read_papers
from survey_system.llm.client import LLMClient
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
from survey_system.paths import pdfs_dir

app = typer.Typer(help="Survey writing system.")
topic_app = typer.Typer(help="Create and inspect topic workspaces.")
run_app = typer.Typer(help="Run survey operations.")
app.add_typer(topic_app, name="topic")
app.add_typer(run_app, name="run")

TopicOption = Annotated[Path, typer.Option("--topic", "-t", exists=False, file_okay=False)]
BibKeyOption = Annotated[str | None, typer.Option("--bib-key", "-k")]
LimitOption = Annotated[int | None, typer.Option("--limit", min=1)]
ForceOption = Annotated[bool, typer.Option("--force")]


def _echo_result(result: OpResult) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


@topic_app.command("init")
def topic_init(topic: TopicOption) -> None:
    topic.mkdir(parents=True, exist_ok=True)
    _echo_result(OpResult.empty("topic.init"))


@topic_app.command("status")
def topic_status_command(topic: TopicOption) -> None:
    typer.echo(json.dumps(topic_status(topic), indent=2, default=str))


@topic_app.command("validate")
def topic_validate(topic: TopicOption) -> None:
    papers = read_papers(topic)
    bib_entries = parse_bib_entries(topic)
    issues: list[str] = []

    if len(papers) != len(bib_entries):
        issues.append(
            f"papers.csv has {len(papers)} rows but references.bib has {len(bib_entries)} entries"
        )

    bib_keys = set(bib_entries)
    paper_keys = {paper.bib_key for paper in papers}
    for missing_key in sorted(paper_keys - bib_keys):
        issues.append(f"references.bib is missing entry for {missing_key}")
    for extra_key in sorted(bib_keys - paper_keys):
        issues.append(f"references.bib has extra entry {extra_key}")

    pdf_dir = pdfs_dir(topic)
    for paper in papers:
        pdf_path = pdf_dir / paper.pdf_filename
        if not pdf_path.exists():
            issues.append(f"missing PDF for {paper.bib_key}: {pdf_path}")

    if issues:
        for issue in issues:
            typer.echo(f"ERROR: {issue}")
        raise typer.Exit(code=1)

    typer.echo("OK: papers.csv, references.bib, and pdf files are consistent")


@topic_app.command("curate-anchors")
def topic_curate_anchors(topic: TopicOption) -> None:
    path = curate_anchors(topic)
    typer.echo(f"Wrote {path}")


@run_app.command("parse-pdf")
def run_parse_pdf(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(parse_pdf.parse_pdf(topic, bib_key=bib_key, limit=limit, force=force))


@run_app.command("round0")
def run_round0(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(parse_pdf.parse_pdf(topic, limit=limit, force=force))


@run_app.command("triage")
def run_triage(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(triage.triage(topic, bib_key=bib_key, limit=limit, force=force))


@run_app.command("round1")
def run_round1(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    client = LLMClient.from_topic(topic)
    triage_result = triage.triage(topic, limit=limit, force=force, llm_client=client)
    l3_result = summarize.summarize_L3(topic, limit=limit, force=force, llm_client=client)
    _echo_result(_combine_results("round1", [triage_result, l3_result]))


@run_app.command("extract")
def run_extract(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(extract.extract_L1(topic, bib_key=bib_key, limit=limit, force=force))


@run_app.command("summarize")
def run_summarize(topic: TopicOption) -> None:
    _echo_result(summarize.summarize(topic))


@run_app.command("summarize-l2")
def run_summarize_l2(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(summarize.summarize_L2(topic, bib_key=bib_key, limit=limit, force=force))


@run_app.command("round4")
def run_round4(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    client = LLMClient.from_topic(topic)
    extract_result = extract.extract_L1(topic, limit=limit, force=force, llm_client=client)
    l2_result = summarize.summarize_L2(topic, limit=limit, force=force, llm_client=client)
    _echo_result(_combine_results("round4", [extract_result, l2_result]))


@run_app.command("propose-anchors")
def run_propose_anchors(topic: TopicOption) -> None:
    _echo_result(propose_anchors.propose_anchors(topic))


@run_app.command("anchors")
def run_anchors(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_result(propose_anchors.propose_anchors(topic, force=force))


@run_app.command("propose-outline")
def run_propose_outline(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_result(propose_outline.propose_outline(topic, force=force))


@run_app.command("round5")
def run_round5(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_result(propose_outline.propose_outline(topic, force=force))


@run_app.command("assign-section")
def run_assign_section(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    _echo_result(assign_section.assign_section(topic, bib_key=bib_key, limit=limit, force=force))


@run_app.command("build-bundles")
def run_build_bundles(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_result(build_bundles.build_bundles(topic, force=force))


@run_app.command("round6")
def run_round6(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    client = LLMClient.from_topic(topic)
    assign_result = assign_section.assign_section(
        topic,
        limit=limit,
        force=force,
        llm_client=client,
    )
    bundle_result = build_bundles.build_bundles(topic, force=force)
    _echo_result(_combine_results("round6", [assign_result, bundle_result]))


@run_app.command("noop")
def run_noop(topic: TopicOption) -> None:
    load_config(topic)
    _echo_result(OpResult.empty("noop"))


def main() -> None:
    app()


def _combine_results(op_name: str, results: list[OpResult]) -> OpResult:
    combined = OpResult(op_name=op_name)
    for result in results:
        combined.processed.extend(result.processed)
        combined.skipped.extend(result.skipped)
        combined.failed.extend(result.failed)
        combined.artifacts_written.extend(result.artifacts_written)
        combined.duration_seconds += result.duration_seconds
    return combined


if __name__ == "__main__":
    main()
