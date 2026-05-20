from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ParsedPdf:
    markdown: str = ""
    images: dict[str, bytes] = field(default_factory=dict)
    page_count: int = 0


class MarkerBackend:
    def __init__(
        self,
        torch_device: str = "auto",
        force_ocr: bool = False,
        use_llm: bool = False,
    ) -> None:
        self.torch_device = torch_device
        self.force_ocr = force_ocr
        self.use_llm = use_llm

    def convert(self, pdf_path: Path) -> ParsedPdf:
        _ = pdf_path
        return ParsedPdf()
