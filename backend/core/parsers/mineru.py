from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from langchain_core.documents import Document

from backend.config import get_settings
from backend.core.logger import get_logger
from backend.core.parsers.base import DocumentParser, ParsedDocument

logger = get_logger(__name__)


# MinerU 4.0 本地支持的主流知识文件类型。
# PDF / 图片可走 basic / standard / advanced；Office 等由 MinerU 自动走本地 Flash。
MINERU_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
        ".doc", ".docx",
        ".ppt", ".pptx",
        ".xls", ".xlsx",
        ".rtf",
        ".odt", ".ods", ".odp",
        ".epub", ".ofd",
        ".html", ".htm",
        ".csv", ".tsv",
    }
)

_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
)
_MODEL_EXTENSIONS = frozenset({".pdf"}) | _IMAGE_EXTENSIONS
_HEADING_ANCHOR_RE = re.compile(r"\s*\[¶\]\([^)]*\)\s*$")


class MinerUUnavailableError(RuntimeError):
    pass


class MinerUParseError(RuntimeError):
    pass


def _first_text(value: Any) -> str:
    """尽量从 MinerU block 的不同结构中提取可检索文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_first_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        # 优先消费常见文本字段，避免把 bbox/score 等噪声写入向量库。
        preferred = (
            "content",
            "text",
            "latex",
            "markdown",
            "html",
            "caption",
            "title",
            "alt",
        )
        parts: list[str] = []
        for key in preferred:
            if key in value:
                text = _first_text(value.get(key))
                if text and text not in parts:
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _block_to_markdown(block: dict) -> tuple[str, str]:
    block_type = str(block.get("type") or "text").lower()
    text = _first_text(block)

    if not text:
        # 图片块可能只有素材引用，没有 OCR/caption；保留类型提示，
        # 让后续多模态/Caption 扩展仍能定位该块。
        asset = (
            block.get("image_path")
            or block.get("image")
            or block.get("src")
            or block.get("path")
        )
        if asset:
            text = f"素材：{asset}"

    if not text:
        return block_type, ""

    if block_type in {"doc_title", "paragraph_title", "section_title"}:
        heading_text = _HEADING_ANCHOR_RE.sub("", text).strip()
        prefix = "#" if block_type == "doc_title" else "##"
        return block_type, f"{prefix} {heading_text}"
    if "equation" in block_type or "formula" in block_type:
        return "formula", f"[公式]\n{text}"
    if "table" in block_type:
        return "table", f"[表格]\n{text}"
    if "image" in block_type or "figure" in block_type or "chart" in block_type:
        return "image", f"[图片]\n{text}"
    if "code" in block_type:
        return "code", f"[代码]\n{text}"

    return block_type, text


class MinerUParser(DocumentParser):
    supported_extensions = MINERU_EXTENSIONS

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        tier: str | None = None,
        output_root: str | Path | None = None,
        timeout_seconds: int | None = None,
        html_image_resolver=None,
    ):
        settings = get_settings()
        self.python_executable = (
            python_executable
            or settings.mineru_python_executable
            or sys.executable
        )
        self.tier = (tier or settings.mineru_tier or "basic").lower()
        self.output_root = Path(
            output_root or settings.mineru_output_root
        ).resolve()
        self.timeout_seconds = int(
            timeout_seconds or settings.mineru_timeout_seconds
        )
        self.worker_script = (
            Path(__file__).resolve().parents[3] / "scripts" / "mineru_parse_worker.py"
        )
        self._html_image_resolver = html_image_resolver

    def _effective_tier(self, path: Path) -> str:
        # MinerU 4 对 Office/OpenDocument/HTML/CSV 等原生文档固定走 Flash。
        if path.suffix.lower() not in _MODEL_EXTENSIONS:
            return "flash"
        return self.tier

    def _output_dir(self, path: Path, document_id: str | None) -> Path:
        safe_id = document_id or path.stem
        return self.output_root / safe_id

    def _run_worker(self, path: Path, output_dir: Path) -> str:
        if not self.worker_script.exists():
            raise MinerUUnavailableError(
                f"MinerU worker 不存在：{self.worker_script}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.python_executable,
            str(self.worker_script),
            "--input",
            str(path),
            "--output",
            str(output_dir),
            "--tier",
            self._effective_tier(path),
        ]

        env = os.environ.copy()
        # 可在 .env.local / 系统环境中设置 modelscope，解决 HF 网络问题。
        if getattr(get_settings(), "mineru_model_source", ""):
            env["MINERU_MODEL_SOURCE"] = get_settings().mineru_model_source

        logger.info(
            "mineru.parse_start",
            source=str(path),
            tier=self._effective_tier(path),
            output=str(output_dir),
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MinerUUnavailableError(
                f"找不到 MinerU Python：{self.python_executable}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MinerUParseError(
                f"MinerU 解析超时（>{self.timeout_seconds}s）：{path.name}"
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            if "No module named 'mineru'" in detail or "No module named \"mineru\"" in detail:
                raise MinerUUnavailableError(
                    "独立 MinerU 环境未安装 mineru>=4.0,<5"
                )
            raise MinerUParseError(
                f"MinerU 解析失败（exit={completed.returncode}）：{detail}"
            )

        logger.info(
            "mineru.parse_done",
            source=str(path),
            output=str(output_dir),
        )
        return completed.stdout.strip()

    def _load_structured_content(
        self,
        path: Path,
        output_dir: Path,
    ) -> list[Document]:
        structured_path = output_dir / "structured_content.json"
        if not structured_path.exists():
            return []

        payload = json.loads(structured_path.read_text(encoding="utf-8"))
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            return []

        docs: list[Document] = []
        for fallback_idx, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            page_idx = page.get("page_idx", fallback_idx)
            try:
                page_idx = int(page_idx)
            except (TypeError, ValueError):
                page_idx = fallback_idx

            block_types: list[str] = []
            parts: list[str] = []
            blocks = page.get("blocks") or []
            if isinstance(blocks, list):
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    block_type, block_text = _block_to_markdown(block)
                    if block_text:
                        parts.append(block_text)
                        block_types.append(block_type)

            page_text = "\n\n".join(parts).strip()
            if not page_text:
                continue

            docs.append(
                Document(
                    page_content=page_text,
                    metadata={
                        "source": str(path),
                        "source_name": f"{path.stem} 第{page_idx + 1}页",
                        "page": page_idx,
                        "parser": "mineru",
                        "content_format": "markdown",
                        "block_types": sorted(set(block_types)),
                        "mineru_output_dir": str(output_dir),
                        "asset_dir": str(output_dir / "images"),
                    },
                )
            )
        return docs

    def _load_markdown_fallback(
        self,
        path: Path,
        output_dir: Path,
    ) -> list[Document]:
        markdown_path = output_dir / "markdown.md"
        if not markdown_path.exists():
            # 兼容可能按源文件名输出 Markdown 的 MinerU 版本。
            candidates = sorted(output_dir.glob("*.md"))
            markdown_path = candidates[0] if candidates else markdown_path

        if not markdown_path.exists():
            return []

        text = markdown_path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        return [
            Document(
                page_content=text,
                metadata={
                    "source": str(path),
                    "source_name": path.stem,
                    "parser": "mineru",
                    "content_format": "markdown",
                    "mineru_output_dir": str(output_dir),
                    "asset_dir": str(output_dir / "images"),
                },
            )
        ]

    @staticmethod
    def _html_image_anchor_candidates(alt: str, target: str) -> list[str]:
        candidates: list[str] = []
        for value in (alt.strip(),):
            if value and value not in candidates:
                candidates.append(value)

        parsed = urlparse(target)
        target_path = unquote(parsed.path or target)
        stem = Path(target_path).stem.strip()
        if stem and stem not in candidates:
            candidates.append(stem)
        return candidates

    @classmethod
    def _inject_html_image_enrichments(cls, docs: list[Document], enrichments) -> None:
        """
        将 HTML 原图的解析文本尽量放回 MinerU Markdown 中对应图片附近。

        MinerU Flash 对 HTML 的正文/代码提取很好，但通常只保留图片 alt/文件名。
        这里复用 Markdown 图片解析链得到的 VLM/OCR 文本；若无法定位锚点，
        则追加到文档末尾的“图片补充信息”区域，避免丢失可检索内容。
        """
        if not docs or not enrichments:
            return

        seen: set[tuple[str, str]] = set()
        pending_blocks: list[str] = []
        for item in enrichments:
            key = (item.target, item.text)
            if key in seen:
                continue
            seen.add(key)

            label = item.alt.strip() or Path(unquote(urlparse(item.target).path)).stem or "未命名图片"
            block = (
                f"\n\n[图片内容：{label}]\n"
                f"{item.text.strip()}\n"
                f"[/图片内容]"
            )
            if any(item.text.strip() in doc.page_content for doc in docs):
                continue

            inserted = False
            for anchor in cls._html_image_anchor_candidates(item.alt, item.target):
                if len(anchor) < 3:
                    continue
                for doc in docs:
                    position = doc.page_content.find(anchor)
                    if position < 0:
                        continue
                    insert_at = position + len(anchor)
                    doc.page_content = (
                        doc.page_content[:insert_at]
                        + block
                        + doc.page_content[insert_at:]
                    )
                    inserted = True
                    break
                if inserted:
                    break

            if not inserted:
                pending_blocks.append(block.strip())

        if pending_blocks:
            docs[-1].page_content = (
                docs[-1].page_content.rstrip()
                + "\n\n## 图片补充信息\n\n"
                + "\n\n".join(pending_blocks)
            )

    def _enrich_html_images(
        self,
        path: Path,
        docs: list[Document],
        *,
        document_id: str | None,
    ):
        if path.suffix.lower() not in {".html", ".htm"}:
            return None

        try:
            raw_html = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning(
                "mineru.html_image_source_read_failed",
                source=str(path),
                error=str(exc),
            )
            return None

        from backend.core.parsers.markdown_images import MarkdownImageResolver

        if not MarkdownImageResolver.contains_images(raw_html):
            return None

        resolver = self._html_image_resolver or MarkdownImageResolver()
        resolution = resolver.enrich(
            raw_html,
            path,
            document_id=document_id or path.stem,
        )
        self._inject_html_image_enrichments(docs, resolution.enrichments)

        for doc in docs:
            doc.metadata.update(
                {
                    "image_count": resolution.image_count,
                    "image_enriched_count": resolution.enriched_count,
                    "image_failed_count": resolution.failed_count,
                    "image_low_value_count": resolution.low_value_count,
                    "image_fallback_count": resolution.fallback_count,
                    "image_tier": resolution.image_tier,
                }
            )
            if resolution.asset_dir:
                doc.metadata["html_image_asset_dir"] = str(resolution.asset_dir)

        logger.info(
            "mineru.html_images_done",
            source=str(path),
            images=resolution.image_count,
            enriched=resolution.enriched_count,
            failed=resolution.failed_count,
            low_value=resolution.low_value_count,
            fallback=resolution.fallback_count,
        )
        return resolution

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")
        if not self.supports(path):
            raise ValueError(f"MinerU 不支持此扩展名：{path.suffix}")

        output_dir = self._output_dir(path, document_id)
        self._run_worker(path, output_dir)

        docs = self._load_structured_content(path, output_dir)
        if not docs:
            docs = self._load_markdown_fallback(path, output_dir)
        if not docs:
            raise MinerUParseError(
                f"MinerU 已执行但未生成可入库内容：{output_dir}"
            )

        html_image_resolution = self._enrich_html_images(
            path,
            docs,
            document_id=document_id,
        )

        image_metadata = {}
        if html_image_resolution is not None:
            image_metadata = {
                "image_count": html_image_resolution.image_count,
                "image_enriched_count": html_image_resolution.enriched_count,
                "image_failed_count": html_image_resolution.failed_count,
                "image_low_value_count": html_image_resolution.low_value_count,
                "image_fallback_count": html_image_resolution.fallback_count,
                "image_tier": html_image_resolution.image_tier,
            }

        return ParsedDocument(
            source_path=path,
            documents=docs,
            parser_name="mineru",
            content_format="markdown",
            output_dir=output_dir,
            asset_dir=output_dir / "images",
            metadata={
                "tier": self._effective_tier(path),
                "document_id": document_id,
                **image_metadata,
            },
        )
