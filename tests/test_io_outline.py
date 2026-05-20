from pathlib import Path

from survey_system.io.outline import parse_outline, parse_outline_text, slugify_section_path


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
