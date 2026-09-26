from __future__ import annotations

import gzip
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from backend.config import get_settings
from backend.core.parsers import get_parser_registry


HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SITEMAP_NAMES = {"sitemap.xml", "sitemap.xml.gz"}


@dataclass(frozen=True)
class UploadedFileEntry:
    """一次上传中已经落盘的文件。"""

    relative_path: str
    absolute_path: Path


@dataclass(frozen=True)
class UploadDiscovery:
    """上传包中哪些文件应该成为知识 Document。"""

    documents: list[UploadedFileEntry]
    asset_count: int
    sitemap_used: bool


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._")
    return cleaned or "default"


def normalize_relative_path(raw_path: str | None, fallback_name: str) -> str:
    """
    将浏览器 webkitRelativePath / 普通文件名归一化为安全的 POSIX 相对路径。

    保留目录层级，但拒绝绝对路径、盘符和 ..，避免上传目录穿越。
    """
    candidate = (raw_path or fallback_name or "").replace("\\", "/").strip()
    if not candidate:
        raise ValueError("上传文件缺少文件名")

    if re.match(r"^[A-Za-z]:", candidate) or candidate.startswith("/"):
        raise ValueError(f"不允许绝对路径：{candidate}")

    path = PurePosixPath(candidate)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"非法相对路径：{candidate}")

    return PurePosixPath(*parts).as_posix()


def get_course_upload_root(tenant_id: str, course_id: str) -> Path:
    settings = get_settings()
    configured = Path(settings.knowledge_upload_root)
    if not configured.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        configured = project_root / configured
    return configured.resolve() / _safe_segment(tenant_id) / _safe_segment(course_id)


def resolve_upload_destination(
    tenant_id: str,
    course_id: str,
    relative_path: str,
) -> Path:
    root = get_course_upload_root(tenant_id, course_id)
    safe_relative = normalize_relative_path(relative_path, Path(relative_path).name)
    destination = (root / Path(*PurePosixPath(safe_relative).parts)).resolve()

    # Python 3.10 兼容写法，确保最终路径仍位于课程目录内。
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("上传路径越界") from exc
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_sitemap_locations(path: Path) -> list[str]:
    try:
        if path.name.lower().endswith(".gz"):
            with gzip.open(path, "rb") as handle:
                payload = handle.read()
        else:
            payload = path.read_bytes()
        root = ET.fromstring(payload)
    except (OSError, ET.ParseError):
        return []

    locations: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "loc":
            continue
        text = (element.text or "").strip()
        if text:
            locations.append(text)
    return locations


def _match_sitemap_html(
    html_entries: list[UploadedFileEntry],
    locations: list[str],
) -> list[UploadedFileEntry]:
    if not html_entries or not locations:
        return []

    normalized = {
        entry.relative_path.lower().replace("\\", "/"): entry
        for entry in html_entries
    }
    selected: dict[str, UploadedFileEntry] = {}

    for location in locations:
        parsed_path = unquote(urlparse(location).path).replace("\\", "/").strip("/")
        if not parsed_path.lower().endswith((".html", ".htm")):
            continue

        path_lower = parsed_path.lower()
        matches = [
            entry
            for rel, entry in normalized.items()
            if rel == path_lower or rel.endswith("/" + path_lower)
        ]

        # 静态站点部署前缀可能与本地目录不同，唯一 basename 作为保守 fallback。
        if not matches:
            basename = PurePosixPath(path_lower).name
            basename_matches = [
                entry
                for rel, entry in normalized.items()
                if PurePosixPath(rel).name == basename
            ]
            if len(basename_matches) == 1:
                matches = basename_matches

        for entry in matches:
            selected[entry.relative_path] = entry

    return list(selected.values())


def _fallback_html_entries(
    html_entries: list[UploadedFileEntry],
) -> list[UploadedFileEntry]:
    filtered: list[UploadedFileEntry] = []
    non_index = [
        entry
        for entry in html_entries
        if PurePosixPath(entry.relative_path).name.lower() not in {"index.html", "index.htm"}
    ]

    for entry in html_entries:
        path = PurePosixPath(entry.relative_path)
        lowered_parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        if name in {"404.html", "404.htm"} or "search" in lowered_parts:
            continue
        # 多页面静态课程的 index 通常只是导航页；只有它是唯一 HTML 时才保留。
        if name in {"index.html", "index.htm"} and non_index:
            continue
        filtered.append(entry)
    return filtered


def discover_ingestible_files(
    entries: list[UploadedFileEntry],
    *,
    folder_mode: bool,
) -> UploadDiscovery:
    """
    从一次上传中挑出真正需要进入 Parser 的知识文件。

    folder 模式下图片作为 HTML/Markdown 的依赖资源保留，不独立建 Document；
    普通文件上传模式则允许图片本身作为知识文档。
    """
    supported = get_parser_registry().supported_extensions
    html_entries = [
        entry for entry in entries
        if entry.absolute_path.suffix.lower() in HTML_EXTENSIONS
    ]

    sitemap_entries = [
        entry
        for entry in entries
        if PurePosixPath(entry.relative_path).name.lower() in SITEMAP_NAMES
    ]
    sitemap_locations: list[str] = []
    for sitemap in sitemap_entries:
        sitemap_locations.extend(_read_sitemap_locations(sitemap.absolute_path))

    sitemap_html = _match_sitemap_html(html_entries, sitemap_locations)
    sitemap_used = bool(sitemap_html)
    selected_html = sitemap_html if sitemap_used else _fallback_html_entries(html_entries)

    selected: dict[str, UploadedFileEntry] = {
        entry.relative_path: entry for entry in selected_html
    }

    for entry in entries:
        ext = entry.absolute_path.suffix.lower()
        if ext not in supported or ext in HTML_EXTENSIONS:
            continue
        if folder_mode and ext in IMAGE_EXTENSIONS:
            continue
        selected[entry.relative_path] = entry

    documents = sorted(selected.values(), key=lambda item: item.relative_path.lower())
    return UploadDiscovery(
        documents=documents,
        asset_count=max(0, len(entries) - len(documents)),
        sitemap_used=sitemap_used,
    )


def remove_empty_parent_dirs(path: Path, *, stop_at: Path) -> None:
    """删除文档文件后，顺手清理上传目录中的空父目录。"""
    current = path.parent
    stop_at = stop_at.resolve()
    while current != stop_at:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
