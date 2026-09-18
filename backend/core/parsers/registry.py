from __future__ import annotations

from pathlib import Path

from backend.core.logger import get_logger
from backend.core.parsers.base import DocumentParser, ParsedDocument
from backend.core.parsers.mineru import (
    MINERU_EXTENSIONS,
    MinerUParseError,
    MinerUParser,
    MinerUUnavailableError,
)
from backend.core.parsers.native import LegacyPdfParser, MarkdownParser, TextParser

logger = get_logger(__name__)


class ParserRegistry:
    """按扩展名选择 Parser；富文档优先 MinerU。"""

    def __init__(self):
        self.markdown = MarkdownParser()
        self.text = TextParser()
        self.mineru = MinerUParser()
        self.pdf_fallback = LegacyPdfParser()

    @property
    def supported_extensions(self) -> set[str]:
        return (
            set(self.markdown.supported_extensions)
            | set(self.text.supported_extensions)
            | set(MINERU_EXTENSIONS)
        )

    def get_parser(self, file_path: str | Path) -> DocumentParser:
        ext = Path(file_path).suffix.lower()
        if ext in self.markdown.supported_extensions:
            return self.markdown
        if ext in self.text.supported_extensions:
            return self.text
        if ext in MINERU_EXTENSIONS:
            return self.mineru

        supported = " / ".join(sorted(self.supported_extensions))
        raise ValueError(
            f"不支持的文件类型：{ext}\n当前支持：{supported}"
        )

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        parser = self.get_parser(file_path)
        try:
            return parser.parse(file_path, document_id=document_id)
        except (MinerUUnavailableError, MinerUParseError) as exc:
            # PDF 可以安全降级到原来的文本层解析；其它富文档不能假装解析成功。
            if Path(file_path).suffix.lower() == ".pdf":
                logger.warning(
                    "mineru.pdf_fallback",
                    source=str(file_path),
                    error=str(exc),
                )
                return self.pdf_fallback.parse(
                    file_path,
                    document_id=document_id,
                )
            raise


_registry: ParserRegistry | None = None


def get_parser_registry() -> ParserRegistry:
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
    return _registry
