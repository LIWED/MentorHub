import json
from pathlib import Path

from langchain_core.documents import Document

from backend.core.parsers.base import ParsedDocument
from backend.core.parsers.markdown_images import MarkdownImageResolver
from backend.core.parsers.mineru import MinerUParser
from backend.core.parsers.native import MarkdownParser
from scripts.build_knowledge_base import split_documents


class FakeImageParser:
    def __init__(self, text: str = "图中展示 Query → Retriever → Reranker → LLM"):
        self.text = text
        self.calls: list[Path] = []

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path)
        self.calls.append(path)
        return ParsedDocument(
            source_path=path,
            documents=[
                Document(
                    page_content=self.text,
                    metadata={"parser": "mineru"},
                )
            ],
            parser_name="mineru",
            content_format="markdown",
        )


class FailingImageParser:
    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        raise RuntimeError("fake image parse failure")


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


def test_markdown_local_image_is_enriched_and_survives_chunking(tmp_path: Path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "rag.png"
    image_path.write_bytes(b"fake-png")

    source = tmp_path / "lesson.md"
    source.write_text(
        "# RAG 架构\n\n下面是系统架构：\n\n"
        "![RAG 架构图](./images/rag.png)\n",
        encoding="utf-8",
    )

    fake_parser = FakeImageParser()
    resolver = MarkdownImageResolver(
        image_parser=fake_parser,
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(
        source,
        document_id="doc-local-image",
    )

    text = parsed.documents[0].page_content
    assert "![RAG 架构图](./images/rag.png)" in text
    assert "[图片内容：RAG 架构图]" in text
    assert "Retriever → Reranker" in text
    assert parsed.metadata["image_count"] == 1
    assert parsed.metadata["image_enriched_count"] == 1
    assert parsed.metadata["image_failed_count"] == 0
    assert parsed.metadata["image_low_value_count"] == 0
    assert parsed.metadata["image_tier"] == "advanced"
    assert fake_parser.calls == [image_path.resolve()]

    chunks = split_documents(parsed.documents, str(source))
    assert any("Retriever → Reranker" in chunk.page_content for chunk in chunks)
    assert all(chunk.metadata.get("image_enriched_count") == 1 for chunk in chunks)


def test_markdown_repeated_image_only_parsed_once(tmp_path: Path):
    image_path = tmp_path / "same.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "lesson.md"
    source.write_text(
        "![第一处](same.png)\n\n正文\n\n![第二处](same.png)",
        encoding="utf-8",
    )

    fake_parser = FakeImageParser("同一张图片的 OCR 文本")
    resolver = MarkdownImageResolver(
        image_parser=fake_parser,
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    text = parsed.documents[0].page_content
    assert len(fake_parser.calls) == 1
    assert parsed.metadata["image_count"] == 2
    assert parsed.metadata["image_enriched_count"] == 2
    assert text.count("同一张图片的 OCR 文本") == 2


def test_markdown_image_failure_keeps_original_reference(tmp_path: Path):
    image_path = tmp_path / "bad.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "lesson.md"
    original = "# 标题\n\n![解析失败图片](bad.png)\n\n后续正文"
    source.write_text(original, encoding="utf-8")

    resolver = MarkdownImageResolver(
        image_parser=FailingImageParser(),
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    assert parsed.documents[0].page_content == original
    assert parsed.metadata["image_count"] == 1
    assert parsed.metadata["image_enriched_count"] == 0
    assert parsed.metadata["image_failed_count"] == 1


def test_markdown_remote_image_is_downloaded_then_parsed(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "remote.md"
    source.write_text(
        "![远程架构图](https://example.com/assets/rag.png)",
        encoding="utf-8",
    )

    fake_parser = FakeImageParser("远程图片 OCR 文本")
    resolver = MarkdownImageResolver(
        image_parser=fake_parser,
        output_root=tmp_path / "mineru",
    )

    def fake_download(url: str, download_dir: Path, cache_hash: str) -> Path:
        assert url == "https://example.com/assets/rag.png"
        download_dir.mkdir(parents=True, exist_ok=True)
        downloaded = download_dir / f"{cache_hash}.png"
        downloaded.write_bytes(b"remote-png")
        return downloaded

    monkeypatch.setattr(resolver, "_download_remote_image", fake_download)
    parsed = MarkdownParser(image_resolver=resolver).parse(
        source,
        document_id="doc-remote-image",
    )

    text = parsed.documents[0].page_content
    assert "[图片内容：远程架构图]" in text
    assert "远程图片 OCR 文本" in text
    assert parsed.metadata["image_enriched_count"] == 1
    assert len(fake_parser.calls) == 1


def test_markdown_html_img_is_enriched(tmp_path: Path):
    image_dir = tmp_path / "img"
    image_dir.mkdir()
    image_path = image_dir / "structure.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "obsidian.md"
    source.write_text(
        '<img src="img/structure.png" alt="项目结构" style="zoom:50%;" />',
        encoding="utf-8",
    )

    fake_parser = FakeImageParser("项目结构包含 backend、frontend 和 scripts")
    resolver = MarkdownImageResolver(
        image_parser=fake_parser,
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    text = parsed.documents[0].page_content
    assert '<img src="img/structure.png"' in text
    assert "[图片内容：项目结构]" in text
    assert "backend、frontend" in text
    assert parsed.metadata["image_count"] == 1
    assert parsed.metadata["image_enriched_count"] == 1
    assert fake_parser.calls == [image_path.resolve()]


def test_markdown_placeholder_only_image_is_not_enriched(tmp_path: Path):
    image_path = tmp_path / "flow.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "lesson.md"
    original = "![流程图](flow.png)"
    source.write_text(original, encoding="utf-8")

    resolver = MarkdownImageResolver(
        image_parser=FakeImageParser("![](images/page_0_image_body_0.jpg)"),
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    assert parsed.documents[0].page_content == original
    assert parsed.metadata["image_enriched_count"] == 0
    assert parsed.metadata["image_low_value_count"] == 1
    assert parsed.metadata["image_failed_count"] == 0


def test_markdown_low_value_vlm_can_fallback_to_ocr(tmp_path: Path):
    image_path = tmp_path / "flow.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "lesson.md"
    source.write_text("![流程图](flow.png)", encoding="utf-8")

    primary = FakeImageParser("![](images/page_0_image_body_0.jpg)")
    fallback = FakeImageParser("Query → Milvus → LLM")
    resolver = MarkdownImageResolver(
        image_parser=primary,
        fallback_image_parser=fallback,
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    assert "Query → Milvus → LLM" in parsed.documents[0].page_content
    assert parsed.metadata["image_enriched_count"] == 1
    assert parsed.metadata["image_fallback_count"] == 1
    assert parsed.metadata["image_low_value_count"] == 0
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_markdown_generic_flowchart_mermaid_is_dropped_but_ocr_is_kept(
    tmp_path: Path,
):
    image_path = tmp_path / "flow.png"
    image_path.write_bytes(b"fake-png")
    source = tmp_path / "lesson.md"
    source.write_text("![流程图](flow.png)", encoding="utf-8")

    fence = chr(96) * 3
    extracted = (
        "Query\nRetriever\nReranker\nLLM\n\n"
        + fence
        + "mermaid\n"
        + 'graph LR\nA["Node 1"] --> B["Node 2"]\n'
        + 'B --> C["Node 3"]\nC --> D["Node 4"]\n'
        + fence
    )
    resolver = MarkdownImageResolver(
        image_parser=FakeImageParser(extracted),
        output_root=tmp_path / "mineru",
    )
    parsed = MarkdownParser(image_resolver=resolver).parse(source)

    text = parsed.documents[0].page_content
    assert "Query" in text
    assert "Retriever" in text
    assert "Node 1" not in text
    assert "mermaid" not in text
    assert parsed.metadata["image_enriched_count"] == 1


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
