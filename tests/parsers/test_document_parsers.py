import json
from pathlib import Path

from langchain_core.documents import Document

from backend.core.parsers.mineru import MinerUParser
from backend.core.parsers.native import MarkdownParser
from scripts.build_knowledge_base import split_documents


def test_markdown_parser_and_splitter_keep_heading_context(tmp_path: Path):
    source = tmp_path / "lesson.md"
    source.write_text(
        "# RAG\n\n正文内容。\n\n## Retrieval\n\nBGE-M3 + BM25 混合检索。",
        encoding="utf-8",
    )

    parsed = MarkdownParser().parse(source)
    chunks = split_documents(parsed.documents, str(source))

    assert parsed.parser_name == "markdown"
    assert chunks
    assert any("RAG" in chunk.metadata.get("source_name", "") for chunk in chunks)
    assert all(chunk.metadata.get("content_format") == "markdown" for chunk in chunks)


def test_mineru_structured_content_preserves_rich_blocks(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-test")

    output = tmp_path / "mineru-output"
    output.mkdir()
    payload = {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {"type": "text", "content": "这是正文"},
                    {"type": "formula", "content": "E = mc^2"},
                    {"type": "table", "content": "|模型|得分|\n|A|90|"},
                    {"type": "image", "caption": "RAG 架构图", "image_path": "images/0.png"},
                ],
            }
        ]
    }
    (output / "structured_content.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    parser = MinerUParser.__new__(MinerUParser)
    docs = parser._load_structured_content(source, output)

    assert len(docs) == 1
    text = docs[0].page_content
    assert "这是正文" in text
    assert "[公式]" in text and "E = mc^2" in text
    assert "[表格]" in text and "|模型|得分|" in text
    assert "[图片]" in text and "RAG 架构图" in text
    assert docs[0].metadata["page"] == 0
    assert set(docs[0].metadata["block_types"]) >= {"text", "formula", "table", "image"}

    chunks = split_documents(docs, str(source))
    assert chunks
    assert all(chunk.metadata.get("parser") == "mineru" for chunk in chunks)
    assert all("第1页" in chunk.metadata.get("source_name", "") for chunk in chunks)


def test_mineru_markdown_fallback(tmp_path: Path):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"pptx-test")
    output = tmp_path / "mineru-output"
    output.mkdir()
    (output / "markdown.md").write_text(
        "# 第一章\n\n公式 $a+b=c$ 与说明。",
        encoding="utf-8",
    )

    parser = MinerUParser.__new__(MinerUParser)
    docs = parser._load_markdown_fallback(source, output)

    assert len(docs) == 1
    assert docs[0].metadata["parser"] == "mineru"
    assert docs[0].metadata["content_format"] == "markdown"
    assert "a+b=c" in docs[0].page_content
