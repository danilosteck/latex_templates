from __future__ import annotations

import pytest

from bibstudio.models import Brief, Deliverable, ResearchQuestion, Theme, Viewpoint
from bibstudio.store import Workspace


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "workspace")


@pytest.fixture
def brief():
    return Brief(
        title="Urban heat islands",
        topic="The effect of urban green roofs on city heat islands",
        disciplines=["urban climatology", "public policy"],
        year_from=2010,
        lit_languages=["en", "pt"],
        output_language="pt-BR",
        rqs=[ResearchQuestion(question="Do green roofs reduce surface temperature?",
                              why="it decides public investment")],
        themes=[Theme(name="green roofs", keywords_en=["green roof", "urban heat"],
                      keywords_other=["telhado verde"])],
        viewpoints=[Viewpoint(label="green infrastructure", description="vegetation first")],
        min_sources=3,
        deliverable=Deliverable(sections=["Executive summary", "Viewpoint map", "References"],
                                max_rounds=1, cost_cap_usd=0.5),
    )
