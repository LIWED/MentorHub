from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from backend.agents.qa import nodes
from backend.agents.qa.graph import _route_after_sufficiency
from backend.core.reranker import RankedDocument


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return _FakeResponse(self.content)


def _doc(
    name: str,
    *,
    score: float = 0.9,
    document_id: str | None = None,
    chunk_index: int = 0,
) -> RankedDocument:
    return RankedDocument(
        content=f"evidence for {name}",
        score=score,
        original_index=0,
        metadata={
            "source_name": f"{name}.md",
            "document_id": document_id or name,
            "chunk_index": chunk_index,
        },
    )


def _state(**overrides) -> dict:
    state = {
        "original_query": "Dense 和 BM25 为什么互补？",
        "rewritten_query": "Dense 和 BM25 为什么互补？",
        "query_type": "SINGLE",
        "tenant_id": "tenant_default",
        "course_id": None,
        "messages": [HumanMessage(content="Dense 和 BM25 为什么互补？")],
        "enable_web_search": False,
        "gap_round": 0,
        "max_gap_rounds": 2,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_single_retrieval_uses_wider_candidate_pool_and_evidence_window(monkeypatch):
    captured = {}

    def fake_retrieve(query, tenant_id, course_id, *, recall_top_k, rerank_top_k):
        captured.update(
            query=query,
            tenant_id=tenant_id,
            course_id=course_id,
            recall_top_k=recall_top_k,
            rerank_top_k=rerank_top_k,
        )
        docs = [_doc(f"d{i}", score=0.95 - i * 0.01) for i in range(rerank_top_k)]
        return docs, docs[0].score

    import backend.core.reranker as reranker
    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    result = await nodes.retrieve_node(_state())

    assert captured["recall_top_k"] == nodes.RECALL_TOP_K_SINGLE == 20
    assert captured["rerank_top_k"] == nodes.RERANK_EVIDENCE_TOP_K == 6
    assert len(result["ranked_chunks"]) == 6
    assert result["evidence_pool"] == result["ranked_chunks"]
    assert result["is_high_confidence"] is True


@pytest.mark.asyncio
async def test_sufficiency_returns_missing_gaps_and_search_hints(monkeypatch):
    llm = _FakeLLM(
        '{"sufficient": false, '
        '"missing_gaps": ["缺少 Dense 与 BM25 互补机制"], '
        '"search_hints": ["dense semantic bm25 lexical complementary"]}'
    )
    monkeypatch.setattr(nodes, "get_llm", lambda *_args, **_kwargs: llm)

    result = await nodes.check_sufficiency_node(
        _state(
            is_high_confidence=True,
            ranked_chunks=[
                {
                    "content": "Dense Retrieval 使用向量语义匹配。",
                    "score": 0.92,
                    "metadata": {"source_name": "rag.md"},
                }
            ],
        )
    )

    assert result["sufficient"] is False
    assert result["missing_gaps"] == ["缺少 Dense 与 BM25 互补机制"]
    assert result["search_hints"] == ["dense semantic bm25 lexical complementary"]


@pytest.mark.asyncio
async def test_gap_retrieve_and_merge_evidence_deduplicate_by_chunk_id(monkeypatch):
    def fake_retrieve(query, *_args, **_kwargs):
        if query == "gap-a":
            return [
                _doc("shared", document_id="doc", chunk_index=1),
                _doc("a", document_id="doc", chunk_index=2),
            ], 0.9
        return [
            _doc("shared", document_id="doc", chunk_index=1),
            _doc("b", document_id="doc", chunk_index=3),
        ], 0.9

    import backend.core.reranker as reranker
    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    state = _state(gap_queries=["gap-a", "gap-b"])
    retrieved = await nodes.gap_retrieve_node(state)

    assert retrieved["gap_round"] == 1
    assert len(retrieved["new_evidence"]) == 3

    merged = await nodes.merge_evidence_node(
        {
            **state,
            **retrieved,
            "evidence_pool": [
                {
                    "content": "old evidence",
                    "score": 0.88,
                    "metadata": {"document_id": "doc", "chunk_index": 0},
                },
                {
                    "content": "older duplicate",
                    "score": 0.50,
                    "metadata": {"document_id": "doc", "chunk_index": 2},
                },
            ],
        }
    )

    assert len(merged["evidence_pool"]) == 4
    assert merged["new_evidence"] == []


def test_sufficiency_route_is_bounded():
    assert _route_after_sufficiency(
        {"sufficient": True, "gap_round": 0, "max_gap_rounds": 2}
    ) == "generate"
    assert _route_after_sufficiency(
        {"sufficient": False, "gap_round": 0, "max_gap_rounds": 2}
    ) == "gap"
    assert _route_after_sufficiency(
        {
            "sufficient": False,
            "gap_round": 2,
            "max_gap_rounds": 2,
            "enable_web_search": True,
        }
    ) == "web"
    assert _route_after_sufficiency(
        {
            "sufficient": False,
            "gap_round": 2,
            "max_gap_rounds": 2,
            "enable_web_search": False,
        }
    ) == "generate_partial"


@pytest.mark.asyncio
async def test_generate_rag_uses_final_context_top_k(monkeypatch):
    llm = _FakeLLM("回答")
    monkeypatch.setattr(nodes, "get_llm", lambda *_args, **_kwargs: llm)

    chunks = [
        {
            "content": f"chunk-{i}",
            "score": 0.99 - i * 0.01,
            "metadata": {"source_name": f"source-{i}.md"},
        }
        for i in range(6)
    ]

    result = await nodes.generate_rag_node(
        _state(ranked_chunks=chunks, confidence=0.99, existing_summary=None)
    )

    prompt = llm.messages[-1].content
    assert "【参考3】" in prompt
    assert "【参考4】" not in prompt
    assert len(result["sources"]) == nodes.FINAL_CONTEXT_TOP_K == 3
