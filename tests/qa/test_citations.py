from backend.agents.qa.nodes import _build_rag_citations


def test_build_rag_citations_preserves_final_context_metadata():
    citations = _build_rag_citations(
        [
            {
                "content": "ReAct 会交替执行 Thought、Action 和 Observation。",
                "score": 0.92341,
                "metadata": {
                    "source_name": "2.4 大模型核心技术ReAct > 四、代码实现",
                    "document_id": "doc-react",
                    "relative_path": "② 核心技术基础/2.4 ReAct.html",
                    "chapter": "2.4 大模型核心技术ReAct",
                    "section": "四、代码实现",
                    "chunk_index": 6,
                    "chunk_type": "text",
                },
            }
        ]
    )

    assert citations == [
        {
            "citation_id": 1,
            "source_name": "2.4 大模型核心技术ReAct > 四、代码实现",
            "document_id": "doc-react",
            "relative_path": "② 核心技术基础/2.4 ReAct.html",
            "chapter": "2.4 大模型核心技术ReAct",
            "section": "四、代码实现",
            "chunk_index": 6,
            "chunk_type": "text",
            "score": 0.9234,
            "excerpt": "ReAct 会交替执行 Thought、Action 和 Observation。",
        }
    ]


def test_build_rag_citations_limits_excerpt_length():
    citations = _build_rag_citations(
        [{"content": "x" * 900, "score": 0.5, "metadata": {}}]
    )

    assert len(citations[0]["excerpt"]) == 700
    assert citations[0]["source_name"] == "课程文档"
