import pytest

from backend.agents.qa import nodes
from backend.core.reranker import RankedDocument


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    async def ainvoke(self, _messages):
        return _FakeResponse("SUFFICIENT")


def _doc(query: str, score: float = 0.9) -> RankedDocument:
    return RankedDocument(
        content=f"evidence for {query}",
        score=score,
        original_index=0,
        metadata={"source_name": f"{query}.md"},
    )


def _base_state(plan: list[dict]) -> dict:
    return {
        "original_query": "测试迭代问题",
        "rewritten_query": "测试迭代问题",
        "query_type": "ITERATIVE",
        "tenant_id": "tenant_default",
        "course_id": None,
        "iterative_plan": plan,
        "enable_web_search": False,
    }


def test_normalize_iterative_plan_limits_to_three_questions():
    raw = {
        "questions": [
            {"id": "x1", "query": "q1", "intent": "i1", "depends_on": []},
            {"id": "x2", "query": "q2", "intent": "i2", "depends_on": ["q1"]},
            {"id": "x3", "query": "q3", "intent": "i3", "depends_on": ["q2"]},
            {"id": "x4", "query": "q4", "intent": "i4", "depends_on": ["q3"]},
        ]
    }

    plan = nodes._normalize_iterative_plan(raw, "fallback")

    assert [item["id"] for item in plan] == ["q1", "q2", "q3"]
    assert len(plan) == 3


@pytest.mark.asyncio
async def test_iterative_retrieval_parallel_dependents_finish_in_two_iterations(monkeypatch):
    plan = [
        {"id": "q1", "query": "seed", "intent": "discover", "depends_on": []},
        {"id": "q2", "query": "detail-a", "intent": "detail-a", "depends_on": ["q1"]},
        {"id": "q3", "query": "detail-b", "intent": "detail-b", "depends_on": ["q1"]},
    ]
    calls: list[str] = []

    async def fake_expand(question, _evidence):
        return [], [question["query"]]

    def fake_retrieve(query, *_args, **_kwargs):
        calls.append(query)
        return [_doc(query)], 0.9

    monkeypatch.setattr(nodes, "_expand_iterative_question", fake_expand)
    monkeypatch.setattr(nodes, "get_llm", lambda *_args, **_kwargs: _FakeLLM())

    import backend.core.reranker as reranker
    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    result = await nodes.iterative_retrieve_node(_base_state(plan))

    assert result["iteration_count"] == 2
    assert calls[0] == "seed"
    assert set(calls[1:]) == {"detail-a", "detail-b"}
    assert result["is_high_confidence"] is True


@pytest.mark.asyncio
async def test_iterative_retrieval_three_level_dependency_uses_three_iterations(monkeypatch):
    plan = [
        {"id": "q1", "query": "seed", "intent": "discover", "depends_on": []},
        {"id": "q2", "query": "second", "intent": "second", "depends_on": ["q1"]},
        {"id": "q3", "query": "third", "intent": "third", "depends_on": ["q2"]},
    ]
    calls: list[str] = []

    async def fake_expand(question, _evidence):
        return [], [question["query"]]

    def fake_retrieve(query, *_args, **_kwargs):
        calls.append(query)
        return [_doc(query)], 0.9

    monkeypatch.setattr(nodes, "_expand_iterative_question", fake_expand)
    monkeypatch.setattr(nodes, "get_llm", lambda *_args, **_kwargs: _FakeLLM())

    import backend.core.reranker as reranker
    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    result = await nodes.iterative_retrieve_node(_base_state(plan))

    assert result["iteration_count"] == 3
    assert calls == ["seed", "second", "third"]
    assert result["is_high_confidence"] is True
