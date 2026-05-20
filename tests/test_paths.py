from pathlib import Path

from survey_system import paths


TOPIC = Path("topic")


def test_topic_paths() -> None:
    assert paths.config_file(TOPIC) == TOPIC / "config.yaml"
    assert paths.papers_csv(TOPIC) == TOPIC / "papers.csv"
    assert paths.references_bib(TOPIC) == TOPIC / "references.bib"
    assert paths.pdfs_dir(TOPIC) == TOPIC / "pdfs"
    assert paths.papers_dir(TOPIC) == TOPIC / "papers"
    assert paths.schemas_dir(TOPIC) == TOPIC / "schemas"
    assert paths.bundles_dir(TOPIC) == TOPIC / "bundles"
    assert paths.outline_path(TOPIC) == TOPIC / "outline.md"
    assert paths.outline_candidates_path(TOPIC) == TOPIC / "outline_candidates_v1.md"
    assert paths.section_assignments_path(TOPIC) == TOPIC / "section_assignments_v1.csv"
    assert paths.anchors_csv(TOPIC) == TOPIC / "anchors.csv"
    assert paths.runs_dir(TOPIC) == TOPIC / "_runs"


def test_paper_artifact_paths() -> None:
    assert paths.paper_artifacts_dir(TOPIC, "key") == TOPIC / "papers" / "key"
    assert paths.paper_l0_path(TOPIC, "key") == TOPIC / "papers" / "key" / "L0.md"
    assert paths.paper_l1_path(TOPIC, "key") == TOPIC / "papers" / "key" / "L1.json"
    assert paths.paper_l2_path(TOPIC, "key") == TOPIC / "papers" / "key" / "L2.md"
    assert paths.paper_l3_path(TOPIC, "key") == TOPIC / "papers" / "key" / "L3.txt"
    assert paths.paper_meta_path(TOPIC, "key") == TOPIC / "papers" / "key" / "meta.json"
    assert paths.paper_images_dir(TOPIC, "key") == TOPIC / "papers" / "key" / "_images"
