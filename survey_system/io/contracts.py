from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel


class FailureItem(BaseModel):
    bib_key: str | None = None
    reason: str


class OpResult(BaseModel):
    op_name: str
    processed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    failed: list[FailureItem] = Field(default_factory=list)
    artifacts_written: list[Path] = Field(default_factory=list)
    duration_seconds: float = 0.0

    @classmethod
    def empty(cls, op_name: str) -> "OpResult":
        return cls(op_name=op_name)


class PaperRow(BaseModel):
    bib_key: str
    title: str
    year: int
    venue: str = ""
    pdf_filename: str
    include: Literal["yes", "no"] = "yes"
    exclusion_reason: str = ""
    user_notes: str = ""


class Meta(BaseModel):
    paper_type: str | None = None
    paper_type_confidence: float | None = None
    tldr: str = ""
    topics: list[str] = Field(default_factory=list)
    anchor: bool = False


class L1Universal(BaseModel):
    schema_version: int = Field(default=1, alias="_schema_version")
    bib_key: str
    fields: dict[str, Any] = Field(default_factory=dict)


class L1ByType(RootModel[dict[str, Any]]):
    root: dict[str, Any] = Field(default_factory=dict)


class L2(BaseModel):
    text: str = ""


class ModelTierConfig(BaseModel):
    cheap: str = "placeholder-cheap"
    capable: str = "placeholder-capable"


class MarkerConfig(BaseModel):
    force_ocr: bool = False
    use_llm: bool = False
    torch_device: str = "auto"
    parse_pdf_min_chars: int = 1000


class TopicConfig(BaseModel):
    topic_name: str
    models: ModelTierConfig = Field(default_factory=ModelTierConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    venue_tiers: dict[str, int] = Field(default_factory=dict)
