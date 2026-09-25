from __future__ import annotations

import asyncio

import pytest

from backend.agents.qa.graph import _timed_node
from backend.agents.qa.timing import (
    build_timing_payload,
    collect_node_timings,
)


@pytest.mark.asyncio
async def test_timed_node_collects_elapsed_time():
    async def fake_node(_state):
        await asyncio.sleep(0.01)
        return {"query_type": "SINGLE"}

    wrapped = _timed_node("classify_query", fake_node)

    with collect_node_timings() as timings:
        result = await wrapped({"session_id": "s1", "query_type": "SINGLE"})

    assert result["query_type"] == "SINGLE"
    assert timings["classify_query"] > 0


@pytest.mark.asyncio
async def test_timing_context_propagates_into_async_task():
    async def fake_node(_state):
        await asyncio.sleep(0.01)
        return {}

    wrapped = _timed_node("retrieve", fake_node)

    with collect_node_timings() as timings:
        await asyncio.create_task(wrapped({"session_id": "s1", "query_type": "SINGLE"}))

    assert timings["retrieve"] > 0


def test_build_timing_payload_uses_readable_labels_and_rounding():
    payload = build_timing_payload(
        {
            "classify_query": 12.345,
            "retrieve": 987.654,
            "generate_rag": 1234.567,
        },
        total_ms=2500.126,
        graph_ms=2300.994,
    )

    assert payload["total_ms"] == 2500.13
    assert payload["graph_ms"] == 2300.99
    assert payload["nodes"] == [
        {"name": "classify_query", "label": "问题分类", "elapsed_ms": 12.35},
        {"name": "retrieve", "label": "知识库检索与重排", "elapsed_ms": 987.65},
        {"name": "generate_rag", "label": "基于知识库生成回答", "elapsed_ms": 1234.57},
    ]


def test_p0_retrieval_nodes_have_readable_timing_labels():
    payload = build_timing_payload(
        {
            "check_sufficiency": 10.0,
            "gap_rewrite": 20.0,
            "gap_retrieve": 30.0,
            "merge_evidence": 1.0,
            "rerank_evidence": 40.0,
        },
        total_ms=101.0,
        graph_ms=100.0,
    )

    assert [item["label"] for item in payload["nodes"]] == [
        "判断证据是否充分",
        "生成缺口检索问题",
        "补充检索缺失证据",
        "合并新旧检索证据",
        "重新排序完整证据",
    ]
