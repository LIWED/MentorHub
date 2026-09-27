from __future__ import annotations

from backend.api.v1 import knowledge


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _Session:
    def __init__(self, row=None):
        self.row = row
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params=None):
        self.queries.append(str(statement))
        return _Result(self.row)


import pytest


@pytest.mark.asyncio
async def test_preview_document_chunks_uses_tenant_scope(monkeypatch):
    session = _Session({"id": "doc-1", "status": "completed"})
    calls: list[tuple[str, str, int]] = []

    class _FakeKB:
        def get_document_chunks(self, document_id, tenant_id, *, limit=200):
            calls.append((document_id, tenant_id, limit))
            return [
                {
                    "id": "chunk-1",
                    "content": "preview",
                    "chunk_index": 0,
                    "source_name": "source",
                    "chunk_type": "text",
                    "document_type": "html",
                    "relative_path": "lesson.html",
                    "chapter": "Lesson",
                    "section": "",
                }
            ]

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(knowledge, "KnowledgeBaseClient", lambda: _FakeKB())

    result = await knowledge.preview_document_chunks(
        "doc-1",
        limit=50,
        current_user={"tenant_id": "tenant-a", "role": "admin"},
    )

    assert calls == [("doc-1", "tenant-a", 50)]
    assert result[0].content == "preview"


@pytest.mark.asyncio
async def test_retrieval_test_runs_full_debug_chain_without_generation(monkeypatch):
    session = _Session()
    captured = {}

    async def fake_run_chain(**kwargs):
        captured.update(
            kwargs
        )
        return {
            "status": "ready_for_rag",
            "strategy": "SINGLE",
            "rewritten_query": kwargs["query"],
            "metadata_scope": {"tenant_id": kwargs["tenant_id"]},
            "scope_source": "tenant",
            "confidence": 0.93,
            "evidence_count": 1,
            "total_ms": 123.4,
            "steps": [
                {
                    "name": "retrieve",
                    "label": "SINGLE 检索",
                    "elapsed_ms": 100.0,
                    "summary": "得到 1 条重排证据",
                    "details": {},
                }
            ],
            "final_evidence": [
                {
                    "rank": 1,
                    "content": "evidence",
                    "score": 0.93,
                    "source_name": "lesson",
                    "document_id": "doc-1",
                    "relative_path": "lesson.html",
                    "chapter": "",
                    "section": "",
                    "chunk_index": 2,
                    "chunk_type": "text",
                }
            ],
            "retrieval_calls": [],
            "runtime_config": {
                "retrieval_confidence_threshold": 0.75,
            },
        }

    import backend.agents.qa.retrieval_debug as retrieval_debug

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        retrieval_debug,
        "run_retrieval_debug_chain",
        fake_run_chain,
    )

    result = await knowledge.retrieval_test(
        knowledge.RetrievalTestRequest(query="ReAct 是什么？"),
        current_user={
            "user_id": "admin-1",
            "tenant_id": "tenant-a",
            "role": "admin",
        },
    )

    assert captured["tenant_id"] == "tenant-a"
    assert captured["student_id"] == "admin-1"
    assert captured["query"] == "ReAct 是什么？"
    assert result.status == "ready_for_rag"
    assert result.steps[0]["name"] == "retrieve"
    assert result.final_evidence[0].score == 0.93
    assert result.confidence == 0.93
