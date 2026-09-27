from backend.core.knowledge_base import KnowledgeBaseClient
from backend.core.reranker import BGEReranker, RankedDocument, retrieve_debug


def test_get_document_chunks_is_tenant_scoped_and_sorted():
    calls = []

    class FakeMilvus:
        def query(self, **kwargs):
            calls.append(kwargs)
            return [
                {
                    "id": "c2",
                    "content": "second",
                    "chunk_index": 2,
                    "document_id": "doc-1",
                },
                {
                    "id": "c0",
                    "content": "first",
                    "chunk_index": 0,
                    "document_id": "doc-1",
                },
            ]

    client = object.__new__(KnowledgeBaseClient)
    client._client = FakeMilvus()

    chunks = client.get_document_chunks("doc-1", "tenant-a", limit=20)

    assert [chunk["chunk_index"] for chunk in chunks] == [0, 2]
    assert 'document_id == "doc-1"' in calls[0]["filter"]
    assert 'tenant_id == "tenant-a"' in calls[0]["filter"]
    assert calls[0]["limit"] == 20
    assert "embedding" not in calls[0]["output_fields"]


def test_retrieve_debug_reuses_hybrid_and_reranker(monkeypatch):
    import backend.core.knowledge_base as kb_module

    class FakeEmbedder:
        def encode_query(self, query):
            assert query == "什么是 ReAct？"
            return [0.1, 0.2]

    class FakeEmbedderClass:
        @classmethod
        def get_instance(cls):
            return FakeEmbedder()

    class FakeKB:
        def _build_filter(self, tenant_id, course_id, metadata_scope=None):
            assert tenant_id == "tenant-a"
            assert course_id == "course-a"
            assert metadata_scope["document_id"] == "doc-react"
            return 'tenant_id == "tenant-a" and document_id == "doc-react"'

        def _hybrid_search(self, query_text, query_embedding, top_k, filters):
            assert query_text == "什么是 ReAct？"
            assert query_embedding == [0.1, 0.2]
            assert top_k == 20
            assert "doc-react" in filters
            return [
                {
                    "content": "candidate",
                    "score": 0.42,
                    "metadata": {
                        "document_id": "doc-react",
                        "chunk_index": 3,
                    },
                }
            ]

    class FakeKBClass:
        def __new__(cls):
            return FakeKB()

    class FakeReranker:
        def rerank_with_confidence(self, query, documents, top_k=3):
            assert top_k == 6
            return [
                RankedDocument(
                    content=documents[0]["content"],
                    score=0.91,
                    original_index=0,
                    metadata=documents[0]["metadata"],
                )
            ], 0.91

    monkeypatch.setattr(kb_module, "BGEMEmbedder", FakeEmbedderClass)
    monkeypatch.setattr(kb_module, "KnowledgeBaseClient", FakeKBClass)
    monkeypatch.setattr(
        BGEReranker,
        "get_instance",
        classmethod(lambda cls: FakeReranker()),
    )

    trace = retrieve_debug(
        "什么是 ReAct？",
        "tenant-a",
        "course-a",
        recall_top_k=20,
        rerank_top_k=6,
        metadata_scope={
            "tenant_id": "tenant-a",
            "course_id": "course-a",
            "document_id": "doc-react",
        },
    )

    assert trace.confidence == 0.91
    assert trace.candidates[0]["score"] == 0.42
    assert trace.ranked_docs[0].score == 0.91
    assert "doc-react" in trace.filter_expr


def test_reranker_scores_retrieval_text_but_returns_raw_content():
    import threading

    captured_pairs = []

    class _Scores:
        def tolist(self):
            return [0.95]

    class _FakeModel:
        def predict(self, pairs):
            captured_pairs.extend(pairs)
            return _Scores()

    reranker = object.__new__(BGEReranker)
    reranker._model = _FakeModel()
    reranker._predict_lock = threading.Lock()

    docs, confidence = reranker.rerank_with_confidence(
        "介绍一下项目",
        [
            {
                "content": "这里是真正的正文。",
                "retrieval_text": (
                    "标题层级：1.1 项目介绍 > 一、背景介绍\n\n"
                    "这里是真正的正文。"
                ),
                "metadata": {"document_id": "doc-1"},
            }
        ],
        top_k=1,
    )

    assert captured_pairs == [
        (
            "介绍一下项目",
            "标题层级：1.1 项目介绍 > 一、背景介绍\n\n这里是真正的正文。",
        )
    ]
    assert confidence == 0.95
    assert docs[0].content == "这里是真正的正文。"
    assert docs[0].retrieval_text.startswith("标题层级：1.1 项目介绍")
