from __future__ import annotations

import json
from pathlib import Path

from survey_system.io.contracts import L1ByType, L1Universal, L2, Meta
from survey_system.io.kb import read_L0, read_meta, write_L1, write_meta


FIXTURE = Path("tests/fixtures/mini_topic")


def test_read_l0() -> None:
    text = read_L0(FIXTURE, "smith2024widgets")

    assert "surveys widget methods" in text


def test_write_and_read_meta(tmp_path: Path) -> None:
    topic = tmp_path / "topic"
    meta = Meta(
        paper_type="survey",
        paper_type_confidence=0.9,
        tldr="A short widget overview.",
        topics=["widgets"],
        anchor=True,
    )

    path = write_meta(topic, "smith2024widgets", meta)

    assert path.exists()
    assert read_meta(topic, "smith2024widgets") == meta


def test_write_l1_model_uses_schema_alias(tmp_path: Path) -> None:
    topic = tmp_path / "topic"
    l1 = L1Universal(bib_key="smith2024widgets", fields={"method": "survey"})

    path = write_L1(topic, "smith2024widgets", l1)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "_schema_version": 1,
        "bib_key": "smith2024widgets",
        "fields": {"method": "survey"},
    }


def test_write_l1_dict(tmp_path: Path) -> None:
    topic = tmp_path / "topic"

    path = write_L1(topic, "lee2023gadgets", {"bib_key": "lee2023gadgets"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"bib_key": "lee2023gadgets"}


def test_phase_one_contracts_accept_loose_content() -> None:
    by_type = L1ByType({"dataset": "FakeSet", "metrics": ["accuracy"]})
    l2 = L2(text="A concise narrative summary.")

    assert by_type.root["dataset"] == "FakeSet"
    assert l2.text == "A concise narrative summary."
