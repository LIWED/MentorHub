"""手动检查知识库文档解析与分块质量，不执行 Embedding 或 Milvus 写入。"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_knowledge_base import parse_document, split_documents  # noqa: E402


def _configure_console() -> None:
    """Windows 终端统一使用 UTF-8，避免中文课件输出乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "测试 EduAgent 文档入库前的解析与分块效果。"
            "只执行 Parser + Chunking，不做 Embedding，也不会写入 Milvus。"
        )
    )
    parser.add_argument("file", help="要测试的文档路径，例如 PDF / HTML / Markdown / Office。")
    parser.add_argument(
        "--document-id",
        default=None,
        help="可选的测试 document_id；默认使用 test-<文件名>。",
    )
    parser.add_argument(
        "--text-preview",
        type=int,
        default=1800,
        help="提取正文预览字符数，默认 1800；0 表示不显示。",
    )
    parser.add_argument(
        "--chunk-preview",
        type=int,
        default=500,
        help="每个 Chunk 的正文预览字符数，默认 500；0 表示只看元数据。",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=20,
        help="最多展示多少个 Chunk，默认 20；0 表示全部展示。",
    )
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="打印完整解析文本，覆盖 --text-preview。",
    )
    parser.add_argument(
        "--full-chunks",
        action="store_true",
        help="打印每个 Chunk 的完整正文，覆盖 --chunk-preview。",
    )
    parser.add_argument(
        "--summary-json",
        default=None,
        help="可选：把统计摘要另存为 JSON 文件，不包含完整正文。",
    )

    args = parser.parse_args()
    source = Path(args.file).expanduser().resolve()
    if not source.exists() or not source.is_file():
        parser.error(f"文件不存在或不是普通文件：{source}")
    if args.text_preview < 0 or args.chunk_preview < 0 or args.max_chunks < 0:
        parser.error("预览长度与 max-chunks 不能为负数。")

    args.file = source
    if not args.document_id:
        args.document_id = f"test-{source.stem}"
    return args


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """只保留人工检查时最有价值的 Chunk 元数据。"""
    preferred = (
        "source_name",
        "chunk_type",
        "code_language",
        "code_split_strategy",
        "code_part_index",
        "code_part_total",
        "H1",
        "H2",
        "H3",
        "H4",
        "page",
        "parser",
        "content_format",
        "image_count",
        "image_enriched_count",
        "image_failed_count",
        "image_low_value_count",
        "image_fallback_count",
        "image_tier",
    )
    return {
        key: metadata[key]
        for key in preferred
        if key in metadata and metadata[key] not in ("", None, [], {})
    }


def _print_rule(title: str) -> None:
    print()
    print("=" * 88)
    print(f" {title}")
    print("=" * 88)


def _preview(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n... <省略 {len(text) - limit} 字符>"


def _build_summary(source: Path, parsed, chunks: list) -> dict[str, Any]:
    all_text = "\n\n".join(doc.page_content for doc in parsed.documents)
    chunk_lengths = [len(chunk.page_content) for chunk in chunks]
    chunk_types = Counter(
        chunk.metadata.get("chunk_type", "text") for chunk in chunks
    )
    code_languages = Counter(
        chunk.metadata.get("code_language")
        for chunk in chunks
        if chunk.metadata.get("chunk_type") == "code"
        and chunk.metadata.get("code_language")
    )

    image_keys = (
        "image_count",
        "image_enriched_count",
        "image_failed_count",
        "image_low_value_count",
        "image_fallback_count",
        "image_tier",
    )
    image_stats = {
        key: parsed.metadata.get(key)
        for key in image_keys
        if parsed.metadata.get(key) is not None
    }

    return {
        "source": str(source),
        "parser": parsed.parser_name,
        "content_format": parsed.content_format,
        "document_count": len(parsed.documents),
        "extracted_characters": len(all_text),
        "parser_metadata": parsed.metadata,
        "image_stats": image_stats,
        "chunk_count": len(chunks),
        "chunk_types": dict(chunk_types),
        "code_languages": {
            str(key): value for key, value in code_languages.items()
        },
        "chunk_length": {
            "min": min(chunk_lengths) if chunk_lengths else 0,
            "max": max(chunk_lengths) if chunk_lengths else 0,
            "avg": round(statistics.mean(chunk_lengths), 1) if chunk_lengths else 0,
        },
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    source: Path = args.file

    print(f"[1/2] 解析文档：{source}")
    parsed = parse_document(str(source), document_id=args.document_id)

    print("[2/2] 执行分块（不会进行 Embedding / Milvus 写入）")
    chunks = split_documents(parsed.documents, str(source))

    summary = _build_summary(source, parsed, chunks)
    all_text = "\n\n".join(doc.page_content for doc in parsed.documents)

    _print_rule("解析摘要")
    print(f"文件             : {summary['source']}")
    print(f"Parser           : {summary['parser']}")
    print(f"Content Format   : {summary['content_format']}")
    print(f"Document 数量    : {summary['document_count']}")
    print(f"提取字符数       : {summary['extracted_characters']}")
    print(f"Chunk 数量       : {summary['chunk_count']}")
    print(f"Chunk 类型       : {summary['chunk_types']}")
    if summary["code_languages"]:
        print(f"代码语言         : {summary['code_languages']}")
    lengths = summary["chunk_length"]
    print(
        "Chunk 长度       : "
        f"min={lengths['min']} / avg={lengths['avg']} / max={lengths['max']}"
    )

    if summary["image_stats"]:
        print("图片统计         :")
        for key, value in summary["image_stats"].items():
            print(f"  - {key}: {value}")

    if parsed.metadata:
        print("Parser Metadata  :")
        print(json.dumps(parsed.metadata, ensure_ascii=False, indent=2, default=str))

    if args.full_text or args.text_preview > 0:
        _print_rule("解析文本")
        text_limit = 0 if args.full_text else args.text_preview
        print(_preview(all_text, text_limit))

    _print_rule("Chunk 明细")
    display_chunks = chunks if args.max_chunks == 0 else chunks[: args.max_chunks]
    for index, chunk in enumerate(display_chunks, start=1):
        metadata = _compact_metadata(chunk.metadata)
        print()
        print(
            f"[Chunk {index}/{len(chunks)}] "
            f"type={metadata.get('chunk_type', 'text')} "
            f"len={len(chunk.page_content)}"
        )
        print(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        preview_limit = 0 if args.full_chunks else args.chunk_preview
        if args.full_chunks or args.chunk_preview > 0:
            print("-" * 60)
            print(_preview(chunk.page_content, preview_limit))

    if len(display_chunks) < len(chunks):
        print()
        print(
            f"... 还有 {len(chunks) - len(display_chunks)} 个 Chunk 未展示；"
            "使用 --max-chunks 0 查看全部。"
        )

    if args.summary_json:
        output_path = Path(args.summary_json).expanduser().resolve()
        _write_summary(output_path, summary)
        print()
        print(f"统计摘要已写入：{output_path}")

    _print_rule("完成")
    print("本脚本仅测试 Parser + Chunking，没有调用 Embedding，也没有写入 Milvus。")
    return 0


def main() -> None:
    _configure_console()
    args = parse_args()
    try:
        raise SystemExit(run(args))
    except KeyboardInterrupt:
        print("\n测试已取消。", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
