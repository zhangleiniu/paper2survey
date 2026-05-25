from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from survey_system.io.tables import paper_matrix_rows, paper_status_rows, write_all_tables


FIXTURE = Path("tests/fixtures/mini_topic")


def test_paper_status_rows_report_pipeline_state(tmp_path: Path) -> None:
    topic = _prepared_topic(tmp_path)

    rows = {row["bib_key"]: row for row in paper_status_rows(topic)}

    smith = rows["smith2024widgets"]
    assert smith["included"] == "yes"
    assert smith["pdf_exists"] == "yes"
    assert smith["L0_exists"] == "yes"
    assert smith["paper_type"] == "survey"
    assert smith["L1_exists"] == "yes"
    assert smith["L1_schema_version"] == "v1"
    assert smith["primary_section"] == "1. Foundations / 1.1 Widget Surveys"
    assert smith["bundle_file"] == "bundles/section_01_1_foundations_1_1_widget_surveys.md"
    assert smith["active_review_reasons"] == ""
    assert "parse_pdf: failed after retry" in smith["stale_review_reasons"]


def test_paper_matrix_rows_expand_current_schema_fields(tmp_path: Path) -> None:
    topic = _prepared_topic(tmp_path)

    rows, fieldnames = paper_matrix_rows(topic)
    smith = next(row for row in rows if row["bib_key"] == "smith2024widgets")

    assert "universal.problem" in fieldnames
    assert "type_specific.survey.scope" in fieldnames
    assert "type_specific.method.method_idea" in fieldnames
    assert smith["paper_type"] == "survey"
    assert smith["universal.problem"] == "Widget methods are hard to compare."
    assert smith["universal.contributions"] == "Unifies widget terminology; Reviews benchmark gaps"
    assert smith["type_specific.survey.scope"] == "Widget algorithm surveys"
    assert smith["type_specific.method.method_idea"] == ""


def test_write_all_tables_creates_status_and_matrix_csvs(tmp_path: Path) -> None:
    topic = _prepared_topic(tmp_path)

    paths = write_all_tables(topic)

    assert [path.name for path in paths] == ["papers.csv", "paper_matrix.csv"]
    assert (topic / "_status" / "papers.csv").exists()
    assert (topic / "_analysis" / "paper_matrix.csv").exists()
    with (topic / "_analysis" / "paper_matrix.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bib_key"] == "smith2024widgets"


def _prepared_topic(tmp_path: Path) -> Path:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    paper_dir = topic / "papers" / "smith2024widgets"
    paper_dir.mkdir(parents=True)
    (paper_dir / "L0.md").write_text("# Widget Survey\n\nBody text.", encoding="utf-8")
    (paper_dir / "L3.txt").write_text("A survey of widget methods.", encoding="utf-8")
    (paper_dir / "L2.md").write_text("This paper reviews widget methods.", encoding="utf-8")
    (paper_dir / "meta.json").write_text(
        json.dumps(
            {
                "paper_type": "survey",
                "paper_type_confidence": 0.95,
                "tldr": "A survey of widget methods.",
                "topics": ["widgets", "surveys"],
                "anchor": True,
            }
        ),
        encoding="utf-8",
    )
    (paper_dir / "L1.json").write_text(
        json.dumps(
            {
                "_schema_version": "v1",
                "_paper_type": "survey",
                "universal": {
                    "problem": "Widget methods are hard to compare.",
                    "contributions": ["Unifies widget terminology", "Reviews benchmark gaps"],
                    "datasets": ["WidgetBench"],
                    "limitations": ["Small empirical section"],
                },
                "type_specific": {
                    "scope": "Widget algorithm surveys",
                    "taxonomy": ["models", "tasks"],
                },
            }
        ),
        encoding="utf-8",
    )
    (topic / "section_assignments_v1.csv").write_text(
        "bib_key,primary_section_path,secondary_section_paths,confidence,reason\n"
        "smith2024widgets,1. Foundations / 1.1 Widget Surveys,,0.9,ok\n",
        encoding="utf-8",
    )
    (topic / "_review_needed.csv").write_text(
        "bib_key,op_name,reason\n"
        "smith2024widgets,parse_pdf,failed after retry: sample failure\n",
        encoding="utf-8",
    )
    return topic
