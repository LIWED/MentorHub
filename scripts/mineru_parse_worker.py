"""
独立 MinerU 入库 Worker。

主 EduAgent 环境不直接依赖 MinerU，避免 MinerU 4.x 的
torch / transformers / pydantic 版本与在线 RAG 环境互相影响。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--tier",
        default="basic",
        choices=("flash", "basic", "standard", "advanced"),
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    from mineru.parser import parse
    from mineru.parser.writer import FileBasedDataWriter

    ext = input_path.suffix.lower()
    if ext == ".pdf":
        result = parse(
            str(input_path),
            tier=args.tier,
            ocr_mode="auto",
            page_range="all",
        )
    elif ext in _IMAGE_EXTENSIONS:
        result = parse(
            str(input_path),
            tier=args.tier,
            ocr_mode="auto",
        )
    else:
        # MinerU 4 原生文档固定使用 Flash。
        result = parse(
            str(input_path),
            tier="flash",
        )

    result.save(FileBasedDataWriter(str(output_dir)))

    print(
        json.dumps(
            {
                "ok": True,
                "input": str(input_path),
                "output": str(output_dir),
                "tier": args.tier if ext == ".pdf" or ext in _IMAGE_EXTENSIONS else "flash",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
