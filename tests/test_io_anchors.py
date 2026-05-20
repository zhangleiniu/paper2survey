from __future__ import annotations

import csv
import shutil
from pathlib import Path

from survey_system.io.anchors import curate_anchors


FIXTURE = Path("tests/fixtures/mini_topic")


def test_curate_anchors_copies_yes_rows(tmp_path: Path) -> None:
    topic = tmp_path / "mini_topic"
    shutil.copytree(FIXTURE, topic)
    (topic / "anchors_candidates_v1.csv").write_text(
        "bib_key,title,year,venue,venue_tier,llm_score,llm_reason,is_survey,suggested,your_decision,role_notes\n"
        "smith2024widgets,Widget Survey,2024,FakeConf,1,5,Core survey,true,true,yes,Best overview\n"
        "lee2023gadgets,Gadget Benchmarks,2023,DemoSymposium,2,3,Useful benchmark,false,false,no,\n",
        encoding="utf-8",
    )

    path = curate_anchors(topic)

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"bib_key": "smith2024widgets", "role_notes": "Best overview"}]
