from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from backend.core.parsers.base import DocumentParser, ParsedDocument
from backend.core.parsers.markdown_images import (
    MarkdownImageResolution,
    MarkdownImageResolver,
)


class MarkdownParser(DocumentParser):
    supported_extensions = frozenset({".md", ".markdown"})

    def __init__(
        self,
        *,
        image_resolver: MarkdownImageResolver | None = None,
    ):
        self._image_resolver = image_resolver

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        docs = TextLoader(str(path), encoding="utf-8").load()
        image_resolution = MarkdownImageResolution(
            text=docs[0].page_content if docs else ""
        )

        if docs and MarkdownImageResolver.contains_images(docs[0].page_content):
            resolver = self._image_resolver or MarkdownImageResolver()
            image_resolution = resolver.enrich(
                docs[0].page_content,
                path,
                document_id=document_id,
            )
            docs[0].page_content = image_resolution.text

        for doc in docs:
            doc.metadata.update(
                {
                    "source": str(path),
                    "source_name": path.stem,
                    "parser": "markdown",
                    "content_format": "markdown",
                    "image_count": image_resolution.image_count,
                    "image_enriched_count": image_resolution.enriched_count,
                    "image_failed_count": image_resolution.failed_count,
                    "image_low_value_count": image_resolution.low_value_count,
                    "image_fallback_count": image_resolution.fallback_count,
                    "image_tier": image_resolution.image_tier,
                }
            )
            if image_resolution.asset_dir:
                doc.metadata["asset_dir"] = str(image_resolution.asset_dir)

        return ParsedDocument(
            source_path=path,
            documents=docs,
            parser_name="markdown",
            content_format="markdown",
            asset_dir=image_resolution.asset_dir,
            metadata={
                "image_count": image_resolution.image_count,
                "image_enriched_count": image_resolution.enriched_count,
                "image_failed_count": image_resolution.failed_count,
                "image_low_value_count": image_resolution.low_value_count,
                "image_fallback_count": image_resolution.fallback_count,
                "image_tier": image_resolution.image_tier,
            },
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
