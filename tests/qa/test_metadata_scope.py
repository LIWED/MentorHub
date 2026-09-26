from __future__ import annotations

import pytest
from langchain_core.documents import Document

from backend.agents.qa import nodes
from backend.core.knowledge_base import KnowledgeBaseClient
from backend.core.reranker import RankedDocument


def _ranked(name: str = "doc", score: float = 0.9) -> RankedDocument:
    return RankedDocument(
        content=f"evidence:{name}",
        score=score,
        original_index=0,
        metadata={
            "document_id": name,
            "chunk_index": 0,
            "source_name": f"{name}.md",
        },
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def test_build_filter_combines_hard_and_metadata_scope():
    expr = KnowledgeBaseClient._build_filter(
        'tenant"one',
        "legacy-course",
        metadata_scope={
            "course_id": "course-1",
            "document_id": "doc-1",
            "chapter": "ReAct",
            "chunk_type": "code",
        },
    )

    assert 'tenant_id == "tenant\\"one"' in expr
    assert 'course_id == "course-1"' in expr
    assert 'document_id == "doc-1"' in expr
    assert 'chapter == "ReAct"' in expr
    assert 'chunk_type == "code"' in expr
    assert "legacy-course" not in expr


def test_document_match_handles_filename_separators():
    assert (
        nodes._document_match_score(
            "Agentic RAG 的检索流程是什么？",
            "2.5 Agentic_RAG.html",
            "② 核心技术基础/2.5 Agentic_RAG.html",
        )
        > 0
    )


@pytest.mark.asyncio
async def test_resolve_scope_soft_matches_unique_document(monkeypatch):
    rows = [
        {
            "id": "doc-react",
            "filename": "2.4 大模型核心技术ReAct.html",
            "relative_path": "② 核心技术基础/2.4 大模型核心技术ReAct.html",
        },
        {
            "id": "doc-rag",
            "filename": "2.3 大模型核心技术RAG.html",
            "relative_path": "② 核心技术基础/2.3 大模型核心技术RAG.html",
        },
    ]

    import backend.dependencies as dependencies

    monkeypatch.setattr(
        dependencies,
        "AsyncSessionLocal",
        lambda: _FakeSession(rows),
    )

    result = await nodes.resolve_scope_node(
        {
            "tenant_id": "tenant-default",
            "course_id": "course-ai",
            "requested_document_id": None,
            "original_query": "ReAct 的代码是怎么实现的？",
            "rewritten_query": "ReAct 的代码是怎么实现的？",
        }
    )

    assert result["metadata_scope"] == {
        "tenant_id": "tenant-default",
        "course_id": "course-ai",
        "document_id": "doc-react",
    }
    assert result["scope_source"] == "query_document"


@pytest.mark.asyncio
async def test_resolve_scope_ambiguous_document_keeps_course_only(monkeypatch):
    rows = [
        {
            "id": "doc-rag",
            "filename": "2.3 RAG.html",
            "relative_path": "课程/2.3 RAG.html",
        },
        {
            "id": "doc-agentic",
            "filename": "2.5 Agentic RAG.html",
            "relative_path": "课程/2.5 Agentic RAG.html",
        },
    ]

    import backend.dependencies as dependencies

    monkeypatch.setattr(
        dependencies,
        "AsyncSessionLocal",
        lambda: _FakeSession(rows),
    )

    result = await nodes.resolve_scope_node(
        {
            "tenant_id": "tenant-default",
            "course_id": "course-ai",
            "requested_document_id": None,
            "original_query": "RAG 是什么？",
            "rewritten_query": "RAG 是什么？",
        }
    )

    assert result["metadata_scope"] == {
        "tenant_id": "tenant-default",
        "course_id": "course-ai",
    }
    assert result["scope_source"] == "course"


@pytest.mark.asyncio
async def test_soft_document_scope_relaxes_only_document_on_zero_hits(monkeypatch):
    calls: list[dict] = []

    def fake_retrieve(
        query,
        tenant_id,
        course_id,
        recall_top_k=10,
        rerank_top_k=3,
        *,
        metadata_scope=None,
    ):
        calls.append(dict(metadata_scope or {}))
        if metadata_scope and metadata_scope.get("document_id"):
            return [], 0.0
        return [_ranked("fallback")], 0.9

    import backend.core.reranker as reranker

    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    results, scope, source = await nodes._retrieve_queries_with_scope(
        {
            "tenant_id": "tenant-default",
            "course_id": "course-ai",
            "metadata_scope": {
                "tenant_id": "tenant-default",
                "course_id": "course-ai",
                "document_id": "doc-react",
            },
            "scope_source": "query_document",
        },
        ["ReAct 实现"],
        recall_top_k=20,
        rerank_top_k=6,
    )

    assert len(calls) == 2
    assert calls[0]["document_id"] == "doc-react"
    assert "document_id" not in calls[1]
    assert calls[1]["course_id"] == "course-ai"
    assert scope == {
        "tenant_id": "tenant-default",
        "course_id": "course-ai",
    }
    assert source == "soft_document_relaxed"
    assert results[0][1][0].metadata["document_id"] == "fallback"


@pytest.mark.asyncio
async def test_explicit_document_scope_never_relaxes(monkeypatch):
    calls: list[dict] = []

    def fake_retrieve(
        query,
        tenant_id,
        course_id,
        recall_top_k=10,
        rerank_top_k=3,
        *,
        metadata_scope=None,
    ):
        calls.append(dict(metadata_scope or {}))
        return [], 0.0

    import backend.core.reranker as reranker

    monkeypatch.setattr(reranker, "retrieve", fake_retrieve)

    results, scope, source = await nodes._retrieve_queries_with_scope(
        {
            "tenant_id": "tenant-default",
            "course_id": "course-ai",
            "metadata_scope": {
                "tenant_id": "tenant-default",
                "course_id": "course-ai",
                "document_id": "doc-explicit",
            },
            "scope_source": "request_document",
        },
        ["只查这个文档"],
        recall_top_k=20,
        rerank_top_k=6,
    )

    assert len(calls) == 1
    assert calls[0]["document_id"] == "doc-explicit"
    assert scope["document_id"] == "doc-explicit"
    assert source == "request_document"
    assert results[0][1] == []


def test_embed_chunks_carries_document_and_section_metadata(monkeypatch):
    from scripts import build_knowledge_base as builder

    class _FakeEmbedder:
        def encode(self, texts, batch_size=12):
            return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(
        builder.BGEMEmbedder,
        "get_instance",
        lambda: _FakeEmbedder(),
    )

    chunks = [
        Document(
            page_content="ReAct code",
            metadata={
                "source_name": "2.4 ReAct > 四、代码实现",
                "chunk_type": "code",
                "H1": "2.4 大模型核心技术ReAct",
                "H2": "四、代码实现",
                "H3": "工具定义",
            },
        )
    ]

    result = builder.embed_chunks(
        chunks,
        course_id="course-ai",
        document_id="doc-react",
        tenant_id="tenant-default",
        document_type="html",
        relative_path="② 核心技术基础/2.4 ReAct.html",
    )

    assert result[0].document_type == "html"
    assert result[0].relative_path == "② 核心技术基础/2.4 ReAct.html"
    assert result[0].chapter == "2.4 大模型核心技术ReAct"
    assert result[0].section == "四、代码实现 > 工具定义"
