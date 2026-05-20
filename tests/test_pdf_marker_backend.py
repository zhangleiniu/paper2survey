from __future__ import annotations

import os
from pathlib import Path

import pytest

from survey_system.pdf.marker_backend import MarkerBackend, ParsedPdf


def test_parsed_pdf_defaults() -> None:
    parsed = ParsedPdf()

    assert parsed.markdown == ""
    assert parsed.images == {}
    assert parsed.page_count == 0


def test_marker_backend_live_fixture() -> None:
    if os.environ.get("RUN_MARKER_LIVE") != "1":
        pytest.skip("set RUN_MARKER_LIVE=1 to run Marker model-backed fixture test")
    pytest.importorskip("marker")

    parsed = MarkerBackend(torch_device="cpu").convert(
        Path("tests/fixtures/mini_topic/pdfs/smith2024widgets.pdf")
    )

    assert isinstance(parsed.markdown, str)
