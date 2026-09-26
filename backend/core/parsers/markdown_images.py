from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urljoin, urlparse

import httpx

from backend.config import get_settings
from backend.core.logger import get_logger
from backend.core.parsers.base import ParsedDocument

logger = get_logger(__name__)


SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
)

_CONTENT_TYPE_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}

# 支持常见 Markdown 图片写法：
# ![alt](./img.png)
# ![alt](https://example.com/img.png "title")
# ![alt](<./path with spaces/img.png>)
_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]"
    r"\(\s*(?P<target><[^>]+>|[^\s)]+)"
    r"(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)

# Obsidian / Markdown 中也常直接使用 HTML img。
_HTML_IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)/?>", re.IGNORECASE | re.DOTALL)
_HTML_SRC_RE = re.compile(
    r"\bsrc\s*=\s*(?:"
    r"(?P<quote>[\"'])(?P<quoted>.*?)(?P=quote)"
    r"|(?P<unquoted>[^\s>]+)"
    r")",
    re.IGNORECASE | re.DOTALL,
)
_HTML_ALT_RE = re.compile(
    r"\balt\s*=\s*(?:"
    r"(?P<quote>[\"'])(?P<quoted>.*?)(?P=quote)"
    r"|(?P<unquoted>[^\s>]+)"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# MinerU 返回这种“只有图片文件引用”的结果时，对文本 RAG 没有检索价值。
_OUTPUT_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\([^)]*\)",
    re.IGNORECASE,
)
_OUTPUT_HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*(?P<body>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_FLOW_NODE_RE = re.compile(r"\bNode\s*\d+\b", re.IGNORECASE)
_PATH_ONLY_LINE_RE = re.compile(
    r"^(?:素材\s*[:：]\s*)?"
    r"(?:images?[\\/]|\.\.?[\\/]|[A-Za-z]:[\\/]|https?://)"
    r".*\.(?:png|jpe?g|webp|bmp|tiff?)$",
    re.IGNORECASE,
)

_MAX_REMOTE_IMAGE_BYTES = 20 * 1024 * 1024
_REMOTE_TIMEOUT_SECONDS = 20.0
_MAX_REDIRECTS = 3
_DEFAULT_IMAGE_TIER = "advanced"
_DEFAULT_FALLBACK_TIER = "basic"


class ImageParser(Protocol):
    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        ...


@dataclass(frozen=True)
class _ImageReference:
    start: int
    end: int
    alt: str
    target: str


@dataclass(frozen=True)
class _CachedImageResult:
    text: str | None
    low_value: bool = False
    failed: bool = False
    used_fallback: bool = False


@dataclass(frozen=True)
class ImageEnrichment:
    """单个图片引用成功提取出的可检索文本。"""

    alt: str
    target: str
    text: str
    used_fallback: bool = False


@dataclass
class MarkdownImageResolution:
    text: str
    image_count: int = 0
    enriched_count: int = 0
    failed_count: int = 0
    low_value_count: int = 0
    fallback_count: int = 0
    asset_dir: Path | None = None
    image_tier: str = _DEFAULT_IMAGE_TIER
    enrichments: list[ImageEnrichment] = field(default_factory=list)


class MarkdownImageResolver:
    """把 Markdown / HTML 图片引用转换为可检索文本。

    Markdown 本体仍由 MarkdownParser 解析；这里只负责：
    1. 找出 Markdown 图片和 HTML <img>
    2. 解析本地相对路径或下载远程图片
    3. 图片优先使用 MinerU advanced（xhigh + image_analysis）解析
    4. advanced 失败或结果只有图片占位符时，用 basic OCR 做轻量降级
    5. 只把真正有文本检索价值的结果写回原 Markdown

    图片解析失败时保留原始 Markdown，不中断整篇文档入库。
    """

    def __init__(
        self,
        *,
        image_parser: ImageParser | None = None,
        fallback_image_parser: ImageParser | None = None,
        image_tier: str = _DEFAULT_IMAGE_TIER,
        fallback_tier: str = _DEFAULT_FALLBACK_TIER,
        output_root: str | Path | None = None,
        max_remote_bytes: int = _MAX_REMOTE_IMAGE_BYTES,
        remote_timeout_seconds: float = _REMOTE_TIMEOUT_SECONDS,
    ):
        settings = get_settings()
        self.output_root = Path(
            output_root or settings.mineru_output_root
        ).resolve()
        self.image_tier = image_tier.strip().lower()
        self.fallback_tier = fallback_tier.strip().lower()
        self.max_remote_bytes = int(max_remote_bytes)
        self.remote_timeout_seconds = float(remote_timeout_seconds)
        self._image_parser = image_parser
        self._fallback_image_parser = fallback_image_parser
        self._primary_parser_injected = image_parser is not None

    @staticmethod
    def _extract_html_attr(
        attrs: str,
        regex: re.Pattern[str],
    ) -> str:
        match = regex.search(attrs)
        if not match:
            return ""
        return (match.group("quoted") or match.group("unquoted") or "").strip()

    @classmethod
    def _find_image_references(cls, text: str) -> list[_ImageReference]:
        refs: list[_ImageReference] = []

        for match in _MARKDOWN_IMAGE_RE.finditer(text):
            refs.append(
                _ImageReference(
                    start=match.start(),
                    end=match.end(),
                    alt=match.group("alt") or "",
                    target=cls._normalize_target(match.group("target")),
                )
            )

        for match in _HTML_IMG_RE.finditer(text):
            attrs = match.group("attrs") or ""
            target = cls._extract_html_attr(attrs, _HTML_SRC_RE)
            if not target:
                continue
            refs.append(
                _ImageReference(
                    start=match.start(),
                    end=match.end(),
                    alt=cls._extract_html_attr(attrs, _HTML_ALT_RE),
                    target=cls._normalize_target(target),
                )
            )

        refs.sort(key=lambda item: (item.start, item.end))

        # 理论上两种语法不会重叠；这里仍做保护，避免重复插入。
        deduped: list[_ImageReference] = []
        last_end = -1
        for ref in refs:
            if ref.start < last_end:
                continue
            deduped.append(ref)
            last_end = ref.end
        return deduped

    @classmethod
    def contains_images(cls, markdown_text: str) -> bool:
        return bool(cls._find_image_references(markdown_text))

    def _get_image_parser(self, parsed_output_root: Path) -> ImageParser:
        if self._image_parser is not None:
            return self._image_parser

        # 延迟 import，避免 native.py <-> mineru.py 的导入耦合。
        from backend.core.parsers.mineru import MinerUParser

        self._image_parser = MinerUParser(
            tier=self.image_tier,
            output_root=parsed_output_root / self.image_tier,
        )
        return self._image_parser

    def _get_fallback_image_parser(
        self,
        parsed_output_root: Path,
    ) -> ImageParser | None:
        if self._fallback_image_parser is not None:
            return self._fallback_image_parser

        # 单元测试显式注入 primary parser 时，默认不偷偷启动真实 MinerU。
        if self._primary_parser_injected:
            return None

        from backend.core.parsers.mineru import MinerUParser

        self._fallback_image_parser = MinerUParser(
            tier=self.fallback_tier,
            output_root=parsed_output_root / self.fallback_tier,
        )
        return self._fallback_image_parser

    @staticmethod
    def _normalize_target(raw_target: str) -> str:
        target = raw_target.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        return target

    @staticmethod
    def _is_remote(target: str) -> bool:
        scheme = urlparse(target).scheme.lower()
        return scheme in {"http", "https"}

    @staticmethod
    def _cache_key(target: str, markdown_path: Path) -> str:
        if MarkdownImageResolver._is_remote(target):
            return target

        if re.match(r"^[A-Za-z]:[\\/]", target):
            return str(Path(unquote(target)).resolve())

        parsed = urlparse(target)
        raw_path = unquote(parsed.path)
        local = Path(raw_path)
        if not local.is_absolute():
            local = markdown_path.parent / local
        return str(local.resolve())

    @staticmethod
    def _safe_image_suffix(path_or_url: str, content_type: str = "") -> str:
        parsed = urlparse(path_or_url)
        suffix = Path(unquote(parsed.path)).suffix.lower()
        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            return suffix

        clean_content_type = content_type.split(";", 1)[0].strip().lower()
        return _CONTENT_TYPE_SUFFIX.get(clean_content_type, "")

    @staticmethod
    def _validate_remote_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"仅支持 http/https 图片 URL：{url}")
        if not parsed.hostname:
            raise ValueError(f"图片 URL 缺少主机名：{url}")

        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            raise ValueError("拒绝访问 localhost 图片地址")

        try:
            addr_info = socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError(f"无法解析图片域名：{parsed.hostname}") from exc

        for item in addr_info:
            address = item[4][0]
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
                or ip.is_multicast
            ):
                raise ValueError(f"拒绝访问非公网图片地址：{address}")

    def _download_remote_image(
        self,
        url: str,
        download_dir: Path,
        cache_hash: str,
    ) -> Path:
        download_dir.mkdir(parents=True, exist_ok=True)
        current_url = url

        with httpx.Client(
            follow_redirects=False,
            timeout=self.remote_timeout_seconds,
            headers={
                "User-Agent": "MentorHub-Knowledge-Ingestion/1.0",
                "Accept": "image/*,*/*;q=0.1",
            },
        ) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                self._validate_remote_url(current_url)

                with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= _MAX_REDIRECTS:
                            raise ValueError("图片 URL 重定向次数过多")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("图片 URL 重定向缺少 Location")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()

                    suffix = self._safe_image_suffix(
                        current_url,
                        response.headers.get("content-type", ""),
                    )
                    if not suffix:
                        raise ValueError(
                            "远程资源不是 MinerU 当前支持的图片类型"
                        )

                    output_path = download_dir / f"{cache_hash}{suffix}"
                    total = 0
                    with output_path.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > self.max_remote_bytes:
                                handle.close()
                                output_path.unlink(missing_ok=True)
                                raise ValueError(
                                    f"远程图片超过大小限制："
                                    f"{self.max_remote_bytes // (1024 * 1024)}MB"
                                )
                            handle.write(chunk)

                    if total == 0:
                        output_path.unlink(missing_ok=True)
                        raise ValueError("远程图片内容为空")
                    return output_path

        raise ValueError("远程图片下载失败")

    @staticmethod
    def _resolve_local_image(markdown_path: Path, target: str) -> Path:
        # Windows 绝对路径如 C:\docs\img.png 会被 urlparse 误识别成 scheme=c。
        if re.match(r"^[A-Za-z]:[\\/]", target):
            image_path = Path(unquote(target))
            if not image_path.exists():
                raise FileNotFoundError(f"Markdown 图片不存在：{image_path}")
            if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ValueError(
                    f"MinerU 当前不支持该 Markdown 图片类型："
                    f"{image_path.suffix.lower()}"
                )
            return image_path.resolve()

        parsed = urlparse(target)
        if parsed.scheme and parsed.scheme.lower() not in {"file"}:
            raise ValueError(f"不支持的本地图片协议：{parsed.scheme}")

        raw_path = unquote(parsed.path)
        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = markdown_path.parent / image_path
        image_path = image_path.resolve()

        if not image_path.exists():
            raise FileNotFoundError(f"Markdown 图片不存在：{image_path}")
        if not image_path.is_file():
            raise ValueError(f"Markdown 图片不是文件：{image_path}")
        if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(
                f"MinerU 当前不支持该 Markdown 图片类型："
                f"{image_path.suffix.lower()}"
            )
        return image_path

    @staticmethod
    def _collect_parsed_text(parsed: ParsedDocument) -> str:
        parts: list[str] = []
        for doc in parsed.documents:
            text = doc.page_content.strip()
            if text and text not in parts:
                parts.append(text)
        return "\n\n".join(parts).strip()

    @staticmethod
    def _useful_text(extracted_text: str) -> str | None:
        """过滤只有图片占位符/素材路径的 MinerU 输出。"""
        if not extracted_text.strip():
            return None

        def _drop_generic_mermaid(match: re.Match[str]) -> str:
            body = match.group("body")
            placeholders = {
                value.lower()
                for value in _GENERIC_FLOW_NODE_RE.findall(body)
            }
            if len(placeholders) >= 3:
                logger.warning(
                    "markdown.flowchart_generic_mermaid_dropped",
                    placeholder_count=len(placeholders),
                )
                return ""
            return match.group(0)

        extracted_text = _MERMAID_BLOCK_RE.sub(
            _drop_generic_mermaid,
            extracted_text,
        )
        cleaned = _OUTPUT_MARKDOWN_IMAGE_RE.sub(" ", extracted_text)
        cleaned = _OUTPUT_HTML_IMG_RE.sub(" ", cleaned)

        useful_lines: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line in {"[图片]", "[/图片]", "[图像]", "[/图像]"}:
                continue
            if _PATH_ONLY_LINE_RE.match(line):
                continue
            useful_lines.append(line)

        candidate = "\n".join(useful_lines).strip()
        semantic_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", candidate)
        if len(semantic_chars) < 3:
            return None
        return candidate

    def _parse_image(
        self,
        image_path: Path,
        *,
        digest: str,
        parsed_output_root: Path,
    ) -> _CachedImageResult:
        primary = self._get_image_parser(parsed_output_root)
        primary_error: Exception | None = None
        primary_low_value = False

        try:
            parsed = primary.parse(
                image_path,
                document_id=f"img_{digest}",
            )
            text = self._useful_text(self._collect_parsed_text(parsed))
            if text:
                return _CachedImageResult(text=text)
            primary_low_value = True
            logger.info(
                "markdown.image_low_value",
                image=str(image_path),
                tier=self.image_tier,
            )
        except Exception as exc:
            primary_error = exc
            logger.warning(
                "markdown.image_primary_failed",
                image=str(image_path),
                tier=self.image_tier,
                error=str(exc),
            )

        fallback = self._get_fallback_image_parser(parsed_output_root)
        if fallback is not None and self.fallback_tier != self.image_tier:
            try:
                parsed = fallback.parse(
                    image_path,
                    document_id=f"img_{digest}_fallback",
                )
                text = self._useful_text(self._collect_parsed_text(parsed))
                if text:
                    return _CachedImageResult(
                        text=text,
                        used_fallback=True,
                    )
            except Exception as exc:
                logger.warning(
                    "markdown.image_fallback_failed",
                    image=str(image_path),
                    tier=self.fallback_tier,
                    error=str(exc),
                )

        if primary_error is not None:
            return _CachedImageResult(text=None, failed=True)
        if primary_low_value:
            return _CachedImageResult(text=None, low_value=True)
        return _CachedImageResult(text=None, failed=True)

    @staticmethod
    def _format_enrichment(alt: str, extracted_text: str) -> str:
        label = alt.strip() or "未命名图片"
        return (
            f"\n\n[图片内容：{label}]\n"
            f"{extracted_text.strip()}\n"
            f"[/图片内容]"
        )

    def enrich(
        self,
        markdown_text: str,
        markdown_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> MarkdownImageResolution:
        source_path = Path(markdown_path).resolve()
        refs = self._find_image_references(markdown_text)
        if not refs:
            return MarkdownImageResolution(
                text=markdown_text,
                image_tier=self.image_tier,
            )

        doc_key = document_id or source_path.stem
        asset_root = self.output_root / doc_key / "markdown_images"
        download_dir = asset_root / "downloads"
        parsed_output_root = asset_root / "parsed"

        # 同一张图片在 Markdown 中重复引用时，只解析一次。
        cache: dict[str, _CachedImageResult] = {}
        enriched_count = 0
        failed_count = 0
        low_value_count = 0
        fallback_count = 0
        enrichments: list[ImageEnrichment] = []
        cursor = 0
        parts: list[str] = []

        for ref in refs:
            parts.append(markdown_text[cursor:ref.end])
            cursor = ref.end

            target = ref.target
            cache_key = self._cache_key(target, source_path)

            if cache_key not in cache:
                digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
                try:
                    if self._is_remote(target):
                        image_path = self._download_remote_image(
                            target,
                            download_dir,
                            digest,
                        )
                    else:
                        image_path = self._resolve_local_image(
                            source_path,
                            target,
                        )

                    cache[cache_key] = self._parse_image(
                        image_path,
                        digest=digest,
                        parsed_output_root=parsed_output_root,
                    )
                except Exception as exc:
                    cache[cache_key] = _CachedImageResult(
                        text=None,
                        failed=True,
                    )
                    logger.warning(
                        "markdown.image_parse_failed",
                        markdown=str(source_path),
                        image=target,
                        error=str(exc),
                    )

            result = cache[cache_key]
            if result.text:
                parts.append(self._format_enrichment(ref.alt, result.text))
                enriched_count += 1
                enrichments.append(
                    ImageEnrichment(
                        alt=ref.alt,
                        target=ref.target,
                        text=result.text,
                        used_fallback=result.used_fallback,
                    )
                )
                if result.used_fallback:
                    fallback_count += 1
            elif result.low_value:
                low_value_count += 1
            elif result.failed:
                failed_count += 1

        parts.append(markdown_text[cursor:])

        return MarkdownImageResolution(
            text="".join(parts),
            image_count=len(refs),
            enriched_count=enriched_count,
            failed_count=failed_count,
            low_value_count=low_value_count,
            fallback_count=fallback_count,
            asset_dir=asset_root,
            image_tier=self.image_tier,
            enrichments=enrichments,
        )
