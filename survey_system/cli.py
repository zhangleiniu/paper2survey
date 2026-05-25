from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from survey_system.config import load_config
from survey_system.io.anchors import curate_anchors
from survey_system.io.assignments import inspect_assignments
from survey_system.io.bib import parse_bib_entries
from survey_system.io.contracts import OpResult
from survey_system.io.outline import inspect_outline
from survey_system.io.papers import read_papers
from survey_system.io.runlog import write_run_log
from survey_system.io.schemas import current_schema_version, inspect_schema_payload, load_schema_payload
from survey_system.io.tables import (
    write_all_tables,
    write_paper_matrix_table,
    write_paper_status_table,
)
from survey_system.llm.client import LLMClient
from survey_system.ops import (
    assign_section,
    build_bundles,
    design_schema,
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
VersionOption = Annotated[str, typer.Option("--version")]
WorkersOption = Annotated[int, typer.Option("--workers", min=1)]


def _echo_result(result: OpResult) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


def _echo_summary(result: OpResult) -> None:
    typer.echo(
        f"{result.op_name}: processed={len(result.processed)} "
        f"skipped={len(result.skipped)} failed={len(result.failed)} "
        f"duration={result.duration_seconds:.1f}s"
    )
    if result.failed:
        typer.echo("Failed papers:")
        for failure in result.failed:
            key = failure.bib_key or "<global>"
            typer.echo(f"  {key}: {failure.reason}")


def _echo_parse_progress(index: int, total: int, paper, status: str) -> None:
    typer.echo(f"[{index}/{total}] {status}: {paper.bib_key}")


def _echo_llm_progress(stage: str, index: int, total: int, paper, status: str) -> None:
    typer.echo(f"{stage} [{index}/{total}] {status}: {paper.bib_key}")


def _echo_logged(topic: Path, result: OpResult) -> None:
    write_run_log(topic, result)
    _refresh_tables_quietly(topic)
    _echo_result(result)


def _refresh_tables_quietly(topic: Path) -> None:
    try:
        write_all_tables(topic)
    except (FileNotFoundError, KeyError, ValueError):
        return


@topic_app.command("init")
def topic_init(topic: TopicOption) -> None:
    topic.mkdir(parents=True, exist_ok=True)
    _echo_result(OpResult.empty("topic.init"))


@topic_app.command("status")
def topic_status_command(
    topic: TopicOption,
    detailed: Annotated[bool, typer.Option("--detailed")] = False,
) -> None:
    status = topic_status(topic, detailed=detailed)
    if detailed:
        typer.echo(f"Topic: {status['topic_name']}")
        typer.echo(f"Included papers: {status['included_papers']}")
        typer.echo(
            f"Review items: {status['review_queue_items']} "
            f"(active={status['active_review_items']}, stale={status['stale_review_items']})"
        )
        typer.echo("Rounds:")
        for name, info in status["rounds"].items():
            typer.echo(f"  {name}: {info}")
        typer.echo("Recent runs:")
        for run in status["recent_runs"]:
            typer.echo(f"  {run.get('op_name')}: {run.get('end_time', '')}")
    else:
        typer.echo(json.dumps(status, indent=2, default=str))


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


@topic_app.command("promote-schema")
def topic_promote_schema(topic: TopicOption, version: VersionOption) -> None:
    path = design_schema.promote_schema(topic, version)
    typer.echo(f"Promoted schema {version}; wrote {path}. Re-run extraction with survey run round4 --force.")


@topic_app.command("inspect-schema")
def topic_inspect_schema(
    topic: TopicOption,
    version: Annotated[str | None, typer.Option("--version")] = None,
) -> None:
    selected_version = version or current_schema_version(topic)
    payload = load_schema_payload(topic, selected_version)
    prior = None
    current_version = current_schema_version(topic)
    if selected_version != current_version:
        prior = load_schema_payload(topic, current_version)
    inspection = inspect_schema_payload(payload, prior=prior)

    typer.echo(f"Schema: {inspection['version']}")
    typer.echo(f"Valid: {str(inspection['valid']).lower()}")
    typer.echo(f"Universal fields ({len(inspection['universal_fields'])}):")
    for field in inspection["universal_fields"]:
        typer.echo(f"  - {field}")
    typer.echo("Paper types:")
    for paper_type, info in inspection["by_type"].items():
        fields = ", ".join(info["fields"])
        bundle = ", ".join(info["bundle_fields"])
        typer.echo(f"  - {paper_type}: fields=[{fields}] bundle=[{bundle}]")
    if inspection["warnings"]:
        typer.echo("Warnings:")
        for warning in inspection["warnings"]:
            typer.echo(f"  - {warning}")
    if inspection["issues"]:
        typer.echo("Issues:")
        for issue in inspection["issues"]:
            typer.echo(f"  - {issue}")
        raise typer.Exit(code=1)


@topic_app.command("inspect-outline")
def topic_inspect_outline(topic: TopicOption) -> None:
    inspection = inspect_outline(topic)
    typer.echo(f"Valid: {str(inspection['valid']).lower()}")
    typer.echo(f"Sections ({inspection['section_count']}):")
    for section in inspection["sections"]:
        typer.echo(f"  - {section}")
    if inspection["candidate_headings"]:
        typer.echo("Candidate headings:")
        for heading in inspection["candidate_headings"]:
            typer.echo(f"  - {heading}")
    if inspection["warnings"]:
        typer.echo("Warnings:")
        for warning in inspection["warnings"]:
            typer.echo(f"  - {warning}")
    if inspection["issues"]:
        typer.echo("Issues:")
        for issue in inspection["issues"]:
            typer.echo(f"  - {issue}")
        raise typer.Exit(code=1)


@topic_app.command("inspect-assignments")
def topic_inspect_assignments(
    topic: TopicOption,
    low_confidence_below: Annotated[float, typer.Option("--low-confidence-below")] = 0.7,
    overloaded_above: Annotated[int, typer.Option("--overloaded-above")] = 5,
) -> None:
    inspection = inspect_assignments(
        topic,
        low_confidence_below=low_confidence_below,
        overloaded_above=overloaded_above,
    )
    typer.echo(f"Valid: {str(inspection['valid']).lower()}")
    typer.echo(f"Assigned: {inspection['assigned']}/{inspection['total']}")
    typer.echo(f"Assignments file: {inspection['path']}")
    typer.echo("Section counts:")
    for section, count in inspection["section_counts"].items():
        typer.echo(f"  - {count}: {section}")
    typer.echo(f"Secondary assignments: {inspection['secondary_count']}")
    if inspection["warnings"]:
        typer.echo("Warnings:")
        for warning in inspection["warnings"]:
            typer.echo(f"  - {warning}")
    if inspection["issues"]:
        typer.echo("Issues:")
        for issue in inspection["issues"]:
            typer.echo(f"  - {issue}")
        raise typer.Exit(code=1)


@topic_app.command("paper-status")
def topic_paper_status(topic: TopicOption) -> None:
    path = write_paper_status_table(topic)
    typer.echo(f"Wrote {path}")


@topic_app.command("paper-matrix")
def topic_paper_matrix(topic: TopicOption) -> None:
    path = write_paper_matrix_table(topic)
    typer.echo(f"Wrote {path}")


@topic_app.command("export-tables")
def topic_export_tables(topic: TopicOption) -> None:
    paths = write_all_tables(topic)
    for path in paths:
        typer.echo(f"Wrote {path}")


@run_app.command("parse-pdf")
def run_parse_pdf(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    result = parse_pdf.parse_pdf(
        topic,
        bib_key=bib_key,
        limit=limit,
        force=force,
        progress_callback=_echo_parse_progress,
    )
    write_run_log(topic, result)
    _refresh_tables_quietly(topic)
    _echo_summary(result)


@run_app.command("round0")
def run_round0(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
) -> None:
    result = parse_pdf.parse_pdf(
        topic,
        limit=limit,
        force=force,
        progress_callback=_echo_parse_progress,
    )
    write_run_log(topic, result)
    _refresh_tables_quietly(topic)
    _echo_summary(result)


@run_app.command("triage")
def run_triage(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    _echo_logged(topic, triage.triage(topic, bib_key=bib_key, limit=limit, force=force, workers=workers))


@run_app.command("round1")
def run_round1(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    client = LLMClient.from_topic(topic)
    triage_result = triage.triage(
        topic,
        limit=limit,
        force=force,
        llm_client=client,
        workers=workers,
        progress_callback=_echo_llm_progress,
    )
    l3_result = summarize.summarize_L3(
        topic,
        limit=limit,
        force=force,
        llm_client=client,
        workers=workers,
        progress_callback=_echo_llm_progress,
    )
    result = _combine_results("round1", [triage_result, l3_result])
    write_run_log(topic, result)
    _refresh_tables_quietly(topic)
    _echo_summary(result)


@run_app.command("extract")
def run_extract(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    _echo_logged(topic, extract.extract_L1(topic, bib_key=bib_key, limit=limit, force=force, workers=workers))


@run_app.command("summarize")
def run_summarize(topic: TopicOption) -> None:
    _echo_logged(topic, summarize.summarize(topic))


@run_app.command("summarize-l2")
def run_summarize_l2(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    _echo_logged(topic, summarize.summarize_L2(topic, bib_key=bib_key, limit=limit, force=force, workers=workers))


@run_app.command("round4")
def run_round4(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    client = LLMClient.from_topic(topic)
    extract_result = extract.extract_L1(topic, limit=limit, force=force, llm_client=client, workers=workers)
    l2_result = summarize.summarize_L2(topic, limit=limit, force=force, llm_client=client, workers=workers)
    _echo_logged(topic, _combine_results("round4", [extract_result, l2_result]))


@run_app.command("propose-anchors")
def run_propose_anchors(topic: TopicOption) -> None:
    _echo_logged(topic, propose_anchors.propose_anchors(topic))


@run_app.command("anchors")
def run_anchors(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_logged(topic, propose_anchors.propose_anchors(topic, force=force))


@run_app.command("schema-design")
def run_schema_design(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_logged(topic, design_schema.design_schema(topic, force=force))


@run_app.command("propose-outline")
def run_propose_outline(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_logged(topic, propose_outline.propose_outline(topic, force=force))


@run_app.command("round5")
def run_round5(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_logged(topic, propose_outline.propose_outline(topic, force=force))


@run_app.command("assign-section")
def run_assign_section(
    topic: TopicOption,
    bib_key: BibKeyOption = None,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    _echo_logged(topic, assign_section.assign_section(topic, bib_key=bib_key, limit=limit, force=force, workers=workers))


@run_app.command("build-bundles")
def run_build_bundles(
    topic: TopicOption,
    force: ForceOption = False,
) -> None:
    _echo_logged(topic, build_bundles.build_bundles(topic, force=force))


@run_app.command("round6")
def run_round6(
    topic: TopicOption,
    limit: LimitOption = None,
    force: ForceOption = False,
    workers: WorkersOption = 1,
) -> None:
    outline_inspection = inspect_outline(topic)
    if not outline_inspection["valid"]:
        typer.echo("ERROR: outline.md is not ready for round6. Run `survey topic inspect-outline` for details.")
        for issue in outline_inspection["issues"]:
            typer.echo(f"  - {issue}")
        raise typer.Exit(code=1)

    client = LLMClient.from_topic(topic)
    assign_result = assign_section.assign_section(
        topic,
        limit=limit,
        force=force,
        llm_client=client,
        workers=workers,
    )
    bundle_result = build_bundles.build_bundles(topic, force=force)
    _echo_logged(topic, _combine_results("round6", [assign_result, bundle_result]))


@run_app.command("noop")
def run_noop(topic: TopicOption) -> None:
    load_config(topic)
    _echo_logged(topic, OpResult.empty("noop"))


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
