"""
单独测试文档解析效果，不写入 Milvus，不做 Embedding。

示例：
    python scripts/test_document_extract.py samples/test.pdf

指定输出目录：
    python scripts/test_document_extract.py samples/test.pdf --output ./tmp/extract_test

只打印前 3000 字：
    python scripts/test_document_extract.py samples/test.pdf --preview 3000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 允许从 scripts/ 直接运行时 import backend.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.parsers import get_parser_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 MentorHub 文档解析")
    parser.add_argument("file", help="要解析的文件路径")
    parser.add_argument(
        "--output",
        help="把统一后的解析结果额外保存到指定目录",
        default=None,
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=2000,
        help="终端预览最大字符数，默认 2000",
    )
    args = parser.parse_args()

    source = Path(args.file).resolve()
    if not source.exists():
        raise FileNotFoundError(f"文件不存在：{source}")

    print("=" * 70)
    print("MentorHub 文档解析测试")
    print(f"文件：{source}")
    print("=" * 70)

    registry = get_parser_registry()
    selected = registry.get_parser(source)
    print(f"Parser：{selected.__class__.__name__}")
    print()

    parsed = registry.parse(
        source,
        document_id=f"test_{source.stem}",
    )

    print("解析结果")
    print(f"  parser_name   : {parsed.parser_name}")
    print(f"  content_format: {parsed.content_format}")
    print(f"  documents     : {len(parsed.documents)}")
    print(f"  output_dir    : {parsed.output_dir}")
    print(f"  asset_dir     : {parsed.asset_dir}")
    print()

    total_chars = sum(len(doc.page_content) for doc in parsed.documents)
    print(f"总文本字符数：{total_chars}")
    print()

    print("-" * 70)
    print("文本预览")
    print("-" * 70)

    remaining = max(args.preview, 0)
    for index, doc in enumerate(parsed.documents, start=1):
        if remaining <= 0:
            break

        content = doc.page_content.strip()
        preview = content[:remaining]

        print(f"\n[Document {index}]")
        print(f"metadata = {json.dumps(doc.metadata, ensure_ascii=False, indent=2)}")
        print()
        print(preview)

        remaining -= len(preview)

    if total_chars > args.preview:
        print(f"\n... 已截断，仅预览前 {args.preview} 字符")

    if args.output:
        output_dir = Path(args.output).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        merged_markdown = "\n\n".join(
            doc.page_content for doc in parsed.documents
        )
        (output_dir / "parsed.md").write_text(
            merged_markdown,
            encoding="utf-8",
        )

        metadata = {
            "source": str(source),
            "parser_name": parsed.parser_name,
            "content_format": parsed.content_format,
            "mineru_output_dir": (
                str(parsed.output_dir) if parsed.output_dir else None
            ),
            "asset_dir": str(parsed.asset_dir) if parsed.asset_dir else None,
            "documents": [
                {
                    "index": index,
                    "metadata": doc.metadata,
                    "chars": len(doc.page_content),
                }
                for index, doc in enumerate(parsed.documents)
            ],
        }

        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print()
        print("-" * 70)
        print("额外输出")
        print(f"  {output_dir / 'parsed.md'}")
        print(f"  {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
