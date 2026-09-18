from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document


@dataclass
class ParsedDocument:
    """统一文档解析结果，供后续 Chunk / Embedding 流水线消费。"""

    source_path: Path
    documents: list[Document]
    parser_name: str
    content_format: str = "text"
    output_dir: Path | None = None
    asset_dir: Path | None = None
    metadata: dict = field(default_factory=dict)


class DocumentParser(ABC):
    """所有知识文件 Parser 的统一接口。"""

    supported_extensions: frozenset[str] = frozenset()

    def supports(self, file_path: str | Path) -> bool:
        return Path(file_path).suffix.lower() in self.supported_extensions

    @abstractmethod
    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        raise NotImplementedError
