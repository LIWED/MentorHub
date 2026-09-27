from types import SimpleNamespace

import pytest

from backend.agents.qa import retrieval_debug


def _runtime():
    return SimpleNamespace(
        recall_top_k_single=20,
        recall_top_k_hyde=20,
        recall_top_k_broad_per=10,
        recall_top_k_iterative=12,
        rerank_evidence_top_k=6,
        final_context_top_k=3,
        retrieval_confidence_threshold=0.75,
        max_gap_queries=2,
        max_gap_rounds=2,
    )


def _chunk(score: float = 0.9):
    return {
        "content": "ReAct evidence",
        "score": score,
        "metadata": {
            "source_name": "2.4 ReAct",
            "document_id": "doc-react",
            "relative_path": "2.4 ReAct.html",
            "chunk_index": 3,
            "chunk_type": "text",
        },
    }


@pytest.mark.asyncio
async def test_full_chain_high_confidence_reaches_sufficiency(monkeypatch):
    async def classify(state):
        return {
            "original_query": "ReAct 是什么？",
            "rewritten_query": "ReAct 是什么？",
            "query_type": "SINGLE",
            "metadata_scope": {"tenant_id": "tenant-a"},
            "scope_source": "tenant",
            "fallback_used": False,
            "gap_round": 0,
            "max_gap_rounds": 2,
            "ranked_chunks": [],
            "evidence_pool": [],
        }

    async def rewrite(state):
        return {"rewritten_query": "ReAct 是什么？"}

    async def resolve_scope(state):
        return {
            "metadata_scope": {
                "tenant_id": "tenant-a",
                "course_id": "course-a",
            },
            "scope_source": "course",
        }

    async def route(state):
        return {"query_type": "SINGLE"}

    async def retrieve(state):
        state["_debug_retrieval_traces"].append(
            {
                "query": state["rewritten_query"],
                "elapsed_ms": 12.3,
                "filter_expr": 'course_id == "course-a"',
                "candidate_count": 20,
                "ranked_docs": [_chunk(0.91)],
                "confidence": 0.91,
                "recall_top_k": 20,
                "rerank_top_k": 6,
            }
        )
        return {
            "ranked_chunks": [_chunk(0.91)],
            "evidence_pool": [_chunk(0.91)],
            "confidence": 0.91,
            "is_high_confidence": True,
        }

    async def sufficiency(state):
        return {
            "sufficient": True,
            "missing_gaps": [],
            "search_hints": [],
        }

    monkeypatch.setattr(retrieval_debug, "_qa_runtime", _runtime)
    monkeypatch.setattr(retrieval_debug, "classify_query_node", classify)
    monkeypatch.setattr(retrieval_debug, "rewrite_query_node", rewrite)
    monkeypatch.setattr(retrieval_debug, "resolve_scope_node", resolve_scope)
    monkeypatch.setattr(retrieval_debug, "structural_router_node", route)
    monkeypatch.setattr(retrieval_debug, "retrieve_node", retrieve)
    monkeypatch.setattr(retrieval_debug, "check_sufficiency_node", sufficiency)

    result = await retrieval_debug.run_retrieval_debug_chain(
        query="ReAct 是什么？",
        tenant_id="tenant-a",
        student_id="admin-1",
        course_id="course-a",
    )

    assert result["status"] == "ready_for_rag"
    assert result["strategy"] == "SINGLE"
    assert result["confidence"] == 0.91
    assert result["evidence_count"] == 1
    assert [step["name"] for step in result["steps"]] == [
        "classify_query",
        "rewrite_query",
        "resolve_scope",
        "structural_router",
        "retrieve",
        "quality_gate",
        "check_sufficiency",
    ]
    assert result["retrieval_calls"][0]["candidate_count"] == 20
    assert result["final_evidence"][0]["document_id"] == "doc-react"


@pytest.mark.asyncio
async def test_low_confidence_chain_runs_hyde_then_stops(monkeypatch):
    async def classify(state):
        return {
            "original_query": "模糊问题",
            "rewritten_query": "模糊问题",
            "query_type": "SINGLE",
            "metadata_scope": {"tenant_id": "tenant-a"},
            "scope_source": "tenant",
            "fallback_used": False,
            "gap_round": 0,
            "max_gap_rounds": 2,
        }

    async def identity(state):
        return {}

    async def route(state):
        return {"query_type": "SINGLE"}

    async def retrieve(state):
        return {
            "ranked_chunks": [_chunk(0.4)],
            "evidence_pool": [_chunk(0.4)],
            "confidence": 0.4,
            "is_high_confidence": False,
        }

    async def hyde_generate(state):
        return {
            "hyde_document": "假想的课程文档内容",
            "fallback_used": True,
        }

    async def hyde_retrieve(state):
        return {
            "ranked_chunks": [_chunk(0.6)],
            "evidence_pool": [_chunk(0.6)],
            "confidence": 0.6,
            "is_high_confidence": False,
            "fallback_used": True,
        }

    monkeypatch.setattr(retrieval_debug, "_qa_runtime", _runtime)
    monkeypatch.setattr(retrieval_debug, "classify_query_node", classify)
    monkeypatch.setattr(
        retrieval_debug,
        "rewrite_query_node",
        lambda state: _async_result({"rewritten_query": "模糊问题"}),
    )
    monkeypatch.setattr(retrieval_debug, "resolve_scope_node", identity)
    monkeypatch.setattr(retrieval_debug, "structural_router_node", route)
    monkeypatch.setattr(retrieval_debug, "retrieve_node", retrieve)
    monkeypatch.setattr(retrieval_debug, "hyde_generate_node", hyde_generate)
    monkeypatch.setattr(retrieval_debug, "hyde_retrieve_node", hyde_retrieve)

    result = await retrieval_debug.run_retrieval_debug_chain(
        query="模糊问题",
        tenant_id="tenant-a",
        student_id="admin-1",
    )

    names = [step["name"] for step in result["steps"]]
    assert result["status"] == "would_direct_fallback"
    assert "hyde_generate" in names
    assert "hyde_retrieve" in names
    assert names.count("quality_gate") == 2


@pytest.mark.asyncio
async def test_insufficient_evidence_runs_gap_loop_then_rechecks(monkeypatch):
    async def classify(state):
        return {
            "original_query": "项目用了哪些数据库，分别做什么？",
            "rewritten_query": "项目用了哪些数据库，分别做什么？",
            "query_type": "SINGLE",
            "metadata_scope": {"tenant_id": "tenant-a"},
            "scope_source": "tenant",
            "fallback_used": False,
            "gap_round": 0,
            "max_gap_rounds": 2,
        }

    async def rewrite(state):
        return {"rewritten_query": state["original_query"]}

    async def route(state):
        return {"query_type": "SINGLE"}

    async def retrieve(state):
        return {
            "ranked_chunks": [_chunk(0.9)],
            "evidence_pool": [_chunk(0.9)],
            "confidence": 0.9,
            "is_high_confidence": True,
        }

    sufficiency_calls = 0

    async def sufficiency(state):
        nonlocal sufficiency_calls
        sufficiency_calls += 1
        if sufficiency_calls == 1:
            return {
                "sufficient": False,
                "missing_gaps": ["缺少第二个数据库用途"],
                "search_hints": ["第二个数据库 用途"],
            }
        return {"sufficient": True, "missing_gaps": [], "search_hints": []}

    async def gap_rewrite(state):
        return {"gap_queries": ["第二个数据库 用途"]}

    async def gap_retrieve(state):
        return {
            "new_evidence": [_chunk(0.86)],
            "gap_round": 1,
        }

    async def merge(state):
        return {
            "evidence_pool": [
                *state.get("evidence_pool", []),
                *state.get("new_evidence", []),
            ],
            "new_evidence": [],
        }

    async def rerank(state):
        return {
            "ranked_chunks": [_chunk(0.92), _chunk(0.86)],
            "confidence": 0.92,
            "is_high_confidence": True,
        }

    monkeypatch.setattr(retrieval_debug, "_qa_runtime", _runtime)
    monkeypatch.setattr(retrieval_debug, "classify_query_node", classify)
    monkeypatch.setattr(retrieval_debug, "rewrite_query_node", rewrite)
    monkeypatch.setattr(
        retrieval_debug,
        "resolve_scope_node",
        lambda state: _async_result({}),
    )
    monkeypatch.setattr(retrieval_debug, "structural_router_node", route)
    monkeypatch.setattr(retrieval_debug, "retrieve_node", retrieve)
    monkeypatch.setattr(retrieval_debug, "check_sufficiency_node", sufficiency)
    monkeypatch.setattr(retrieval_debug, "gap_rewrite_node", gap_rewrite)
    monkeypatch.setattr(retrieval_debug, "gap_retrieve_node", gap_retrieve)
    monkeypatch.setattr(retrieval_debug, "merge_evidence_node", merge)
    monkeypatch.setattr(retrieval_debug, "rerank_evidence_node", rerank)

    result = await retrieval_debug.run_retrieval_debug_chain(
        query="项目用了哪些数据库，分别做什么？",
        tenant_id="tenant-a",
        student_id="admin-1",
    )

    names = [step["name"] for step in result["steps"]]
    assert result["status"] == "ready_for_rag"
    assert sufficiency_calls == 2
    assert "gap_rewrite" in names
    assert "gap_retrieve" in names
    assert "merge_evidence" in names
    assert "rerank_evidence" in names


async def _async_result(value):
    return value
