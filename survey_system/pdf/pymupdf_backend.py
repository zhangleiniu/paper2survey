from __future__ import annotations

from pathlib import Path

from survey_system.pdf.marker_backend import ParsedPdf


class PyMuPDFBackend:
    def convert(self, pdf_path: Path) -> ParsedPdf:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is not installed") from exc

        document = fitz.open(pdf_path)
        pages: list[str] = []
        for index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            pages.append(f"## Page {index}\n\n{text}")
        return ParsedPdf(markdown="\n\n".join(pages).strip() + "\n", page_count=len(document))
