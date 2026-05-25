from __future__ import annotations

import shutil
from pathlib import Path

from survey_system.io.contracts import Meta
from survey_system.io.kb import write_L1, write_L2, write_meta
from survey_system.ops.build_bundles import build_bundles


FIXTURE = Path("tests/fixtures/mini_topic")


def test_build_bundles_writes_markdown_with_anchors_first(tmp_path: Path) -> None:
    topic = _topic_with_bundle_inputs(tmp_path)

    result = build_bundles(topic)

    assert "1. Foundations / 1.1 Widget Surveys" in result.processed
    bundle = topic / "bundles" / "section_01_1_foundations_1_1_widget_surveys.md"
    text = bundle.read_text(encoding="utf-8")
    assert "## Anchor Papers" in text
    assert "Widget Survey (`smith2024widgets`)" in text
    assert '"scope": "Widget methods"' in text
    assert "smith2024widgets" in text


def test_build_bundles_includes_cross_references(tmp_path: Path) -> None:
    topic = _topic_with_bundle_inputs(tmp_path)

    build_bundles(topic)

    text = (topic / "bundles" / "section_03_2_systems_2_1_tool_workflows.md").read_text(
        encoding="utf-8"
    )
    assert "## Cross-references" in text
    assert "Widget Survey (`smith2024widgets`)" in text


def test_build_bundles_is_idempotent(tmp_path: Path) -> None:
    topic = _topic_with_bundle_inputs(tmp_path)

    build_bundles(topic)
    second = build_bundles(topic)

    assert second.processed == []
    assert second.skipped == [
        "1. Foundations / 1.1 Widget Surveys",
        "1. Foundations / 1.2 Gadget Benchmarks",
        "2. Systems / 2.1 Tool Workflows",
    ]


def test_build_bundles_without_anchors_uses_papers_block(tmp_path: Path) -> None:
    topic = _topic_with_bundle_inputs(tmp_path)
    (topic / "anchors.csv").unlink()

    build_bundles(topic)

    text = (topic / "bundles" / "section_01_1_foundations_1_1_widget_surveys.md").read_text(
        encoding="utf-8"
    )
    assert "## Anchor Papers" not in text
    assert "## Papers" in text


def test_build_bundles_force_removes_stale_bundle_files(tmp_path: Path) -> None:
    topic = _topic_with_bundle_inputs(tmp_path)
    stale = topic / "bundles" / "section_99_old_outline.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")

    result = build_bundles(topic, force=True)

    assert not stale.exists()
    assert "stale_bundle:section_99_old_outline.md" in result.processed
    assert (topic / "bundles" / "section_01_1_foundations_1_1_widget_surveys.md").exists()


def _topic_with_bundle_inputs(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "anchors.csv").write_text("bib_key,role_notes\nsmith2024widgets,core\n", encoding="utf-8")
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,2. Systems / 2.1 Tool Workflows,0.9,ok\n"
        "lee2023gadgets,1. Foundations / 1.2 Gadget Benchmarks,,0.9,ok\n"
        "patel2022systems,2. Systems / 2.1 Tool Workflows,,0.9,ok\n",
        encoding="utf-8",
    )
    payloads = {
        "smith2024widgets": (
            "survey",
            {
                "scope": "Widget methods",
                "taxonomy": ["methods", "benchmarks"],
            },
        ),
        "lee2023gadgets": (
            "benchmark",
            {
                "benchmark_goal": "Compare gadget systems",
                "metrics": ["accuracy"],
            },
        ),
        "patel2022systems": (
            "tool_system",
            {
                "system_goal": "Support workflows",
                "interface_or_workflow": "Command workflow",
            },
        ),
    }
    for bib_key, (paper_type, type_specific) in payloads.items():
        write_meta(topic, bib_key, Meta(paper_type=paper_type, paper_type_confidence=0.9))
        write_L2(topic, bib_key, f"Full L2 narrative for {bib_key}.")
        write_L1(
            topic,
            bib_key,
            {
                "_schema_version": "v1",
                "_paper_type": paper_type,
                "universal": {
                    "problem": "Fixture problem",
                    "contributions": ["Fixture contribution"],
                    "datasets": [],
                    "limitations": ["Fixture limitation"],
                },
                "type_specific": type_specific,
            },
        )
    return topic
