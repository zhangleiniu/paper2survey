from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any


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
        self._converter: Any | None = None

    def convert(self, pdf_path: Path) -> ParsedPdf:
        converter = self._get_converter()
        rendered = converter(str(pdf_path))

        try:
            from marker.output import text_from_rendered
        except ImportError as exc:
            raise RuntimeError(
                "marker-pdf is not installed. Install with: pip install -e '.[marker]'"
            ) from exc

        markdown, _, images = text_from_rendered(rendered)
        return ParsedPdf(
            markdown=markdown,
            images=_normalize_images(images),
            page_count=_page_count(rendered),
        )

    def _get_converter(self):
        if self._converter is not None:
            return self._converter

        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
        except ImportError as exc:
            raise RuntimeError(
                "marker-pdf is not installed. Install with: pip install -e '.[marker]'"
            ) from exc

        config = {
            "force_ocr": self.force_ocr,
            "use_llm": self.use_llm,
            "output_format": "markdown",
        }
        if self.torch_device != "auto":
            config["torch_device"] = self.torch_device

        try:
            artifacts = create_model_dict(device=self.torch_device)
        except TypeError:
            artifacts = create_model_dict()

        try:
            self._converter = PdfConverter(artifact_dict=artifacts, config=config)
        except TypeError:
            self._converter = PdfConverter(artifact_dict=artifacts)

        return self._converter


def _normalize_images(images: Any) -> dict[str, bytes]:
    if not images:
        return {}

    normalized: dict[str, bytes] = {}
    for name, image in dict(images).items():
        filename = str(name)
        if not Path(filename).suffix:
            filename = f"{filename}.png"

        if isinstance(image, bytes):
            normalized[filename] = image
            continue

        if hasattr(image, "save"):
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            normalized[filename] = buffer.getvalue()

    return normalized


def _page_count(rendered: Any) -> int:
    metadata = getattr(rendered, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("page_count", "pages"):
            value = metadata.get(key)
            if isinstance(value, int):
                return value

    pages = getattr(rendered, "pages", None)
    if pages is not None:
        try:
            return len(pages)
        except TypeError:
            return 0

    return 0
