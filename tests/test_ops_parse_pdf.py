from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from survey_system.ops import parse_pdf as parse_pdf_module
from survey_system.ops.parse_pdf import parse_pdf
from survey_system.pdf.marker_backend import ParsedPdf


FIXTURE = Path("tests/fixtures/mini_topic")


class FakeBackend:
    instances = 0

    def __init__(self, *args, **kwargs) -> None:
        FakeBackend.instances += 1
        self.calls: list[Path] = []

    def convert(self, pdf_path: Path) -> ParsedPdf:
        self.calls.append(pdf_path)
        stem = pdf_path.stem
        return ParsedPdf(
            markdown=f"# {stem}\n\nParsed paragraph for {stem}.\n\n![Figure](_images/{stem}.png)\n",
            images={f"{stem}.png": b"image-bytes"},
            page_count=1,
        )


class ShortBackend:
    def convert(self, pdf_path: Path) -> ParsedPdf:
        return ParsedPdf(markdown="# x\n", images={}, page_count=1)


class FlakyBackend:
    def __init__(self) -> None:
        self.calls = 0

    def convert(self, pdf_path: Path) -> ParsedPdf:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return ParsedPdf(markdown="# recovered\n\nEnough text.", images={}, page_count=1)


class BrokenBackend:
    def __init__(self) -> None:
        self.calls = 0

    def convert(self, pdf_path: Path) -> ParsedPdf:
        self.calls += 1
        raise RuntimeError("password protected or corrupt")


@pytest.fixture()
def topic(tmp_path: Path) -> Path:
    copied = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, copied)
    return copied


def test_parse_pdf_processes_included_papers(topic: Path) -> None:
    backend = FakeBackend()

    result = parse_pdf(topic, backend=backend)

    assert result.processed == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    assert result.skipped == []
    assert len(backend.calls) == 3
    l0 = topic / "papers" / "smith2024widgets" / "L0.md"
    image = topic / "papers" / "smith2024widgets" / "_images" / "smith2024widgets.png"
    assert "# smith2024widgets" in l0.read_text(encoding="utf-8")
    assert not image.exists()


def test_parse_pdf_saves_images_when_enabled(topic: Path) -> None:
    _set_marker_save_images(topic)
    backend = FakeBackend()

    parse_pdf(topic, bib_key="smith2024widgets", backend=backend)

    image = topic / "papers" / "smith2024widgets" / "_images" / "smith2024widgets.png"
    assert image.read_bytes() == b"image-bytes"


def test_parse_pdf_is_idempotent_and_force_reprocesses(topic: Path) -> None:
    first_backend = FakeBackend()
    second_backend = FakeBackend()
    forced_backend = FakeBackend()

    first = parse_pdf(topic, backend=first_backend)
    second = parse_pdf(topic, backend=second_backend)
    forced = parse_pdf(topic, backend=forced_backend, force=True)

    assert len(first.processed) == 3
    assert second.processed == []
    assert second.skipped == ["smith2024widgets", "lee2023gadgets", "patel2022systems"]
    assert len(second_backend.calls) == 0
    assert len(forced.processed) == 3
    assert len(forced_backend.calls) == 3


def test_parse_pdf_limit(topic: Path) -> None:
    backend = FakeBackend()

    result = parse_pdf(topic, limit=1, backend=backend)

    assert result.processed == ["smith2024widgets"]
    assert len(backend.calls) == 1


def test_parse_pdf_reports_progress(topic: Path) -> None:
    progress = []

    parse_pdf(
        topic,
        limit=2,
        backend=FakeBackend(),
        progress_callback=lambda index, total, paper, status: progress.append(
            (index, total, paper.bib_key, status)
        ),
    )

    assert progress == [
        (1, 2, "smith2024widgets", "processed"),
        (2, 2, "lee2023gadgets", "processed"),
    ]


def test_parse_pdf_missing_pdf_is_reviewed(topic: Path) -> None:
    (topic / "pdfs" / "lee2023gadgets.pdf").unlink()

    result = parse_pdf(topic, bib_key="lee2023gadgets", backend=FakeBackend())

    assert result.failed[0].bib_key == "lee2023gadgets"
    review_rows = _review_rows(topic)
    assert review_rows[0]["bib_key"] == "lee2023gadgets"
    assert "missing PDF" in review_rows[0]["reason"]


def test_parse_pdf_short_l0_is_reviewed(topic: Path) -> None:
    result = parse_pdf(topic, bib_key="smith2024widgets", backend=ShortBackend())

    assert result.processed == ["smith2024widgets"]
    review_rows = _review_rows(topic)
    assert "shorter than parse_pdf_min_chars" in review_rows[0]["reason"]


def test_parse_pdf_retries_marker_exception(topic: Path) -> None:
    backend = FlakyBackend()

    result = parse_pdf(topic, bib_key="smith2024widgets", backend=backend)

    assert result.processed == ["smith2024widgets"]
    assert backend.calls == 2


def test_parse_pdf_flags_marker_failure_after_retry(topic: Path) -> None:
    backend = BrokenBackend()

    result = parse_pdf(topic, bib_key="smith2024widgets", backend=backend)

    assert result.failed[0].bib_key == "smith2024widgets"
    assert backend.calls == 2
    assert "PDF parsing failed after retry" in _review_rows(topic)[0]["reason"]


def test_cli_instantiates_marker_backend_once(topic: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from survey_system.cli import app

    FakeBackend.instances = 0
    monkeypatch.setattr(parse_pdf_module, "MarkerBackend", FakeBackend)

    result = CliRunner().invoke(app, ["run", "round0", "--topic", str(topic)])

    assert result.exit_code == 0
    assert FakeBackend.instances == 1


def test_cli_round0_prints_progress_summary(topic: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from survey_system.cli import app

    monkeypatch.setattr(parse_pdf_module, "MarkerBackend", FakeBackend)

    result = CliRunner().invoke(app, ["run", "round0", "--topic", str(topic)])

    assert result.exit_code == 0
    assert "[1/3] processed: smith2024widgets" in result.output
    assert "parse_pdf: processed=3 skipped=0 failed=0" in result.output
    assert '"processed": [' not in result.output


def _review_rows(topic: Path) -> list[dict[str, str]]:
    with (topic / "_review_needed.csv").open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _set_marker_save_images(topic: Path) -> None:
    config = topic / "config.yaml"
    text = config.read_text(encoding="utf-8")
    text = text.replace("  parse_pdf_min_chars: 10", "  save_images: true\n  parse_pdf_min_chars: 10")
    config.write_text(text, encoding="utf-8")
