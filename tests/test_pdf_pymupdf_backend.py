from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from survey_system.pdf.pymupdf_backend import PyMuPDFBackend


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text(self, mode: str) -> str:
        return self.text


class FakeDocument:
    def __iter__(self):
        return iter([FakePage("First page"), FakePage("Second page")])

    def __len__(self) -> int:
        return 2


def test_pymupdf_backend_conforms_to_parsed_pdf(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=lambda path: FakeDocument()))

    parsed = PyMuPDFBackend().convert(Path("fake.pdf"))

    assert parsed.page_count == 2
    assert "## Page 1" in parsed.markdown
    assert "Second page" in parsed.markdown
