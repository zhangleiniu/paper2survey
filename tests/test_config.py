from pathlib import Path

from survey_system.config import load_config


FIXTURE = Path("tests/fixtures/mini_topic")


def test_load_config() -> None:
    config = load_config(FIXTURE)

    assert config.topic_name == "mini_topic"
    assert config.marker.force_ocr is False
    assert config.marker.torch_device == "cpu"
    assert config.marker.parse_pdf_min_chars == 10
    assert config.venue_tiers["FakeConf"] == 1
