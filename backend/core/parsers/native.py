from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from backend.core.parsers.base import DocumentParser, ParsedDocument


class MarkdownParser(DocumentParser):
    supported_extensions = frozenset({".md", ".markdown"})

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        docs = TextLoader(str(path), encoding="utf-8").load()
        for doc in docs:
            doc.metadata.update(
                {
                    "source": str(path),
                    "source_name": path.stem,
                    "parser": "markdown",
                    "content_format": "markdown",
                }
            )
        return ParsedDocument(
            source_path=path,
            documents=docs,
            parser_name="markdown",
            content_format="markdown",
        )


class TextParser(DocumentParser):
    supported_extensions = frozenset({".txt"})

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        docs = TextLoader(str(path), encoding="utf-8").load()
        for doc in docs:
            doc.metadata.update(
                {
                    "source": str(path),
                    "source_name": path.stem,
                    "parser": "text",
                    "content_format": "text",
                }
            )
        return ParsedDocument(
            source_path=path,
            documents=docs,
            parser_name="text",
            content_format="text",
        )


class LegacyPdfParser(DocumentParser):
    """MinerU 不可用时的 PDF 文本层降级解析器。"""

    supported_extensions = frozenset({".pdf"})

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        pages = PyPDFLoader(str(path)).load()
        for page in pages:
            page_num = int(page.metadata.get("page", 0)) + 1
            page.metadata.update(
                {
                    "source": str(path),
                    "source_name": f"{path.stem} 第{page_num}页",
                    "parser": "pypdf_fallback",
                    "content_format": "text",
                }
            )
        return ParsedDocument(
            source_path=path,
            documents=pages,
            parser_name="pypdf_fallback",
            content_format="text",
            metadata={"fallback": True},
        )
