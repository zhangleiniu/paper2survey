from __future__ import annotations

from pathlib import Path


def topic_root(topic_path: Path) -> Path:
    return Path(topic_path)


def config_file(topic_path: Path) -> Path:
    return topic_root(topic_path) / "config.yaml"


def papers_csv(topic_path: Path) -> Path:
    return topic_root(topic_path) / "papers.csv"


def references_bib(topic_path: Path) -> Path:
    return topic_root(topic_path) / "references.bib"


def pdfs_dir(topic_path: Path) -> Path:
    return topic_root(topic_path) / "pdfs"


def papers_dir(topic_path: Path) -> Path:
    return topic_root(topic_path) / "papers"


def paper_artifacts_dir(topic_path: Path, bib_key: str) -> Path:
    return papers_dir(topic_path) / bib_key


def paper_l0_path(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "L0.md"


def paper_l1_path(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "L1.json"


def paper_l2_path(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "L2.md"


def paper_l3_path(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "L3.txt"


def paper_meta_path(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "meta.json"


def paper_images_dir(topic_path: Path, bib_key: str) -> Path:
    return paper_artifacts_dir(topic_path, bib_key) / "_images"


def schemas_dir(topic_path: Path) -> Path:
    return topic_root(topic_path) / "schemas"


def bundles_dir(topic_path: Path) -> Path:
    return topic_root(topic_path) / "bundles"


def outline_path(topic_path: Path) -> Path:
    return topic_root(topic_path) / "outline.md"


def outline_candidates_path(topic_path: Path, version: str = "v1") -> Path:
    return topic_root(topic_path) / f"outline_candidates_{version}.md"


def section_assignments_path(topic_path: Path, version: str = "v1") -> Path:
    return topic_root(topic_path) / f"section_assignments_{version}.csv"


def anchors_csv(topic_path: Path) -> Path:
    return topic_root(topic_path) / "anchors.csv"


def runs_dir(topic_path: Path) -> Path:
    return topic_root(topic_path) / "_runs"


def review_needed_csv(topic_path: Path) -> Path:
    return topic_root(topic_path) / "_review_needed.csv"
