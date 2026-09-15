import asyncio

import pytest

from backend.agents.resume import nodes
from backend.agents.resume.state import DimensionScore
from backend.agents.resume.timing import collect_timings


@pytest.mark.asyncio
async def test_extract_text_node_preserves_result_and_records_timing(monkeypatch):
    expected = {"raw_text": "真实文本" * 100, "page_count": 2}
    monkeypatch.setattr(nodes, "_sync_extract_text", lambda _: expected)

    with collect_timings() as timings:
        result = await nodes.extract_text_node({"pdf_local_path": "unused.pdf"})

    assert result == expected
    assert timings["extract_text"] >= 0


@pytest.mark.asyncio
async def test_six_dimensions_node_preserves_order_score_and_records_timings(monkeypatch):
    class FakeStructuredLLM:
        def __init__(self):
            self.entered = 0
            self.all_entered = asyncio.Event()

        async def ainvoke(self, _messages):
            self.entered += 1
            if self.entered == 6:
                self.all_entered.set()
            await asyncio.wait_for(self.all_entered.wait(), timeout=1.0)
            return DimensionScore(score=80, issues=[], suggestions=[])

    fake_llm = FakeStructuredLLM()
    monkeypatch.setattr(nodes, "get_structured_llm", lambda *_args: fake_llm)

    with collect_timings() as timings:
        result = await nodes.run_six_dimensions_node({"raw_text": "resume", "structured": {}})

    assert len(result["dimension_scores"]) == 6
    assert [item["key"] for item in result["dimension_scores"]] == [
        dimension["key"] for dimension in nodes.SIX_DIMENSIONS
    ]
    assert result["weighted_score"] == 80.0
    assert fake_llm.entered == 6
    assert timings["six_dimensions"] >= 0
    for dimension in nodes.SIX_DIMENSIONS:
        assert timings[f"dimension.{dimension['key']}"] >= 0
