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


PaperType = Literal[
    "survey",
    "method",
    "benchmark",
    "dataset",
    "analysis",
    "position",
    "application",
    "tool_system",
]
PAPER_TYPES: tuple[str, ...] = (
    "survey",
    "method",
    "benchmark",
    "dataset",
    "analysis",
    "position",
    "application",
    "tool_system",
)


class Meta(BaseModel):
    paper_type: PaperType | None = None
    paper_type_confidence: float = 0.0
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
    triage: str | None = None
    extract: str | None = None
    summarize: str | None = None
    schema_design: str | None = None
    outline: str | None = None
    assign: str | None = None
    provider: str = "anthropic"


class ThresholdConfig(BaseModel):
    triage_confidence_review_below: float = 0.7
    assign_confidence_review_below: float = 0.7


class MarkerConfig(BaseModel):
    backend: str = "marker"
    force_ocr: bool = False
    use_llm: bool = False
    torch_device: str = "auto"
    save_images: bool = False
    parse_pdf_min_chars: int = 1000


class VertexAIConfig(BaseModel):
    project: str | None = None
    location: str = "global"
    thinking_budget: int | None = None


class TopicConfig(BaseModel):
    topic_name: str
    models: ModelTierConfig = Field(default_factory=ModelTierConfig)
    vertexai: VertexAIConfig = Field(default_factory=VertexAIConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    venue_tiers: dict[str, int] = Field(default_factory=dict)
