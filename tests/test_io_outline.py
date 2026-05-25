from pathlib import Path

from survey_system.io.outline import (
    inspect_outline_text,
    parse_outline,
    parse_outline_text,
    slugify_section_path,
)


FIXTURE = Path("tests/fixtures/mini_topic")


def test_parse_outline_extracts_leaf_sections() -> None:
    sections = parse_outline(FIXTURE)

    assert [section.path for section in sections] == [
        "1. Foundations / 1.1 Widget Surveys",
        "1. Foundations / 1.2 Gadget Benchmarks",
        "2. Systems / 2.1 Tool Workflows",
    ]
    assert sections[0].slug == "1_foundations_1_1_widget_surveys"


def test_parse_outline_uses_h2_when_no_h3() -> None:
    sections = parse_outline_text("## Standalone Section\n\nText\n\n## Trade-offs\n\nNope")

    assert [section.path for section in sections] == ["Standalone Section"]


def test_slugify_section_path() -> None:
    assert slugify_section_path("3.2 Dynamic Detection") == "3_2_dynamic_detection"


def test_inspect_outline_accepts_final_outline() -> None:
    inspection = inspect_outline_text("## Foundations\n\n### Core Ideas\n")

    assert inspection["valid"] is True
    assert inspection["sections"] == ["Foundations / Core Ideas"]
    assert inspection["issues"] == []


def test_inspect_outline_rejects_candidate_output() -> None:
    inspection = inspect_outline_text(
        "# Candidate 1: A\n\n## Foundations\n\n### Core Ideas\n\n"
        "## Trade-offs\n\ntext\n\n# Candidate 2: B\n\n## Methods\n\n### Tools\n"
    )

    assert inspection["valid"] is False
    assert inspection["candidate_headings"] == ["# Candidate 1: A", "# Candidate 2: B"]
    assert any("candidate headings" in issue for issue in inspection["issues"])
    assert inspection["warnings"] == ["outline.md still contains a Trade-offs section from proposal output"]
