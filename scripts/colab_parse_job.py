"""
Standalone Colab-side parser for one MentorHub development job.

This file intentionally avoids importing the MentorHub backend package so the
Colab worker only needs MinerU and the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}
_HTML_IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.IGNORECASE)
_HTML_SRC_RE = re.compile(
    r"""\bsrc\s*=\s*(?:["'](?P<quoted>[^"']+)["']|(?P<unquoted>[^\s>]+))""",
    re.IGNORECASE,
)
_HTML_ALT_RE = re.compile(
    r"""\balt\s*=\s*(?:["'](?P<quoted>[^"']*)["']|(?P<unquoted>[^\s>]+))""",
    re.IGNORECASE,
)
_FLOWCHART_IMAGE_PROMPT_SUFFIX = """
For flowcharts, architecture diagrams, process diagrams, and pipeline diagrams:
- Preserve every visible node label exactly as written in the image.
- Preserve arrow direction and branch labels such as Yes/No or true/false.
- Output valid Mermaid using the real visible labels.
- Never replace visible labels with placeholders such as "Node 1", "Node 2", "Step 1", etc.
- Do not invent edges that are not clearly visible.
- If an edge or label is ambiguous, omit that uncertain relation instead of guessing.
- Prefer an incomplete but faithful graph over a complete but fabricated graph.
"""


def _attr(attrs: str, regex: re.Pattern[str]) -> str:
    match = regex.search(attrs)
    if not match:
        return ""
    return (match.group("quoted") or match.group("unquoted") or "").strip()


def _run_mineru(input_path: Path, output_dir: Path, tier: str) -> None:
    from mineru.parser import parse
    from mineru.parser.writer import FileBasedDataWriter

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = input_path.suffix.lower()

    if ext in _IMAGE_EXTENSIONS and tier == "advanced":
        from mineru_vl_utils.mineru_client import DEFAULT_PROMPTS

        for key in ("image", "chart"):
            base_prompt = DEFAULT_PROMPTS.get(key, "\nImage Analysis:")
            if _FLOWCHART_IMAGE_PROMPT_SUFFIX.strip() not in base_prompt:
                DEFAULT_PROMPTS[key] = (
                    base_prompt.rstrip()
                    + "\n"
                    + _FLOWCHART_IMAGE_PROMPT_SUFFIX.strip()
                )

    if ext == ".pdf":
        result = parse(
            str(input_path),
            tier=tier,
            ocr_mode="auto",
            page_range="all",
        )
    elif ext in _IMAGE_EXTENSIONS:
        result = parse(
            str(input_path),
            tier=tier,
            ocr_mode="auto",
        )
    else:
        result = parse(str(input_path), tier="flash")

    result.save(FileBasedDataWriter(str(output_dir)))


def _load_markdown(output_dir: Path) -> str:
    candidates = [
        output_dir / "markdown.md",
        *sorted(output_dir.glob("*.md")),
    ]
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
    return ""


def _useful_image_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"[图片]", "[/图片]", "[图像]", "[/图像]"}:
            continue
        if re.fullmatch(r"!?\[[^\]]*\]\([^\)]+\)", line):
            continue
        if re.fullmatch(r"[^\s]+\.(?:png|jpe?g|webp|bmp|tiff?)", line, re.I):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_image(image_path: Path, output_root: Path, image_key: str) -> tuple[str, bool]:
    advanced_dir = output_root / "image_parse" / "advanced" / image_key
    _run_mineru(image_path, advanced_dir, "advanced")
    text = _useful_image_text(_load_markdown(advanced_dir))
    if text:
        return text, False

    basic_dir = output_root / "image_parse" / "basic" / image_key
    _run_mineru(image_path, basic_dir, "basic")
    return _useful_image_text(_load_markdown(basic_dir)), True


def _inject_html_images(
    source_path: Path,
    markdown: str,
    output_root: Path,
) -> tuple[str, dict]:
    try:
        html = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return markdown, {
            "image_count": 0,
            "image_enriched_count": 0,
            "image_failed_count": 0,
            "image_low_value_count": 0,
            "image_fallback_count": 0,
            "image_tier": "advanced",
        }

    refs: list[tuple[str, str]] = []
    for match in _HTML_IMG_RE.finditer(html):
        attrs = match.group("attrs") or ""
        target = _attr(attrs, _HTML_SRC_RE)
        if target:
            refs.append((_attr(attrs, _HTML_ALT_RE), target))

    enriched = 0
    failed = 0
    low_value = 0
    fallback = 0
    pending: list[str] = []
    seen: set[str] = set()

    for index, (alt, target) in enumerate(refs):
        parsed = urlparse(target)
        if parsed.scheme.lower() in {"http", "https"}:
            failed += 1
            continue
        raw_path = unquote(parsed.path)
        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = source_path.parent / image_path
        image_path = image_path.resolve()

        cache_key = str(image_path)
        if cache_key in seen:
            continue
        seen.add(cache_key)

        if not image_path.is_file() or image_path.suffix.lower() not in _IMAGE_EXTENSIONS:
            failed += 1
            continue

        try:
            image_text, used_fallback = _parse_image(
                image_path,
                output_root,
                f"{index:04d}-{image_path.stem}",
            )
        except Exception:
            failed += 1
            continue

        if used_fallback:
            fallback += 1
        if not image_text:
            low_value += 1
            continue

        enriched += 1
        label = alt.strip() or image_path.stem or "未命名图片"
        block = f"\n\n[图片内容：{label}]\n{image_text}\n[/图片内容]"
        anchors = [value for value in (alt.strip(), image_path.stem.strip()) if len(value) >= 3]
        inserted = False
        for anchor in anchors:
            position = markdown.find(anchor)
            if position < 0:
                continue
            insert_at = position + len(anchor)
            markdown = markdown[:insert_at] + block + markdown[insert_at:]
            inserted = True
            break
        if not inserted:
            pending.append(block.strip())

    if pending:
        markdown = (
            markdown.rstrip()
            + "\n\n## 图片补充信息\n\n"
            + "\n\n".join(pending)
        )

    return markdown, {
        "image_count": len(refs),
        "image_enriched_count": enriched,
        "image_failed_count": failed,
        "image_low_value_count": low_value,
        "image_fallback_count": fallback,
        "image_tier": "advanced",
    }


def parse_job(job_root: Path, output_root: Path) -> dict:
    manifest = json.loads((job_root / "job.json").read_text(encoding="utf-8"))
    source_path = (
        job_root / "source" / str(manifest["source_relpath"])
    ).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"job source missing: {source_path}")

    # 所有 MinerU 中间产物只留在 Colab 本地；写回 Drive 的结果 ZIP
    # 只包含 result.json / markdown.md / structured_content.json，避免同步大量小文件。
    work_dir = output_root / "_work"
    mineru_dir = work_dir / "mineru"
    _run_mineru(source_path, mineru_dir, str(manifest.get("tier") or "basic"))
    markdown = _load_markdown(mineru_dir)
    if not markdown:
        raise RuntimeError("MinerU did not produce markdown content")

    image_metadata = {}
    if source_path.suffix.lower() in {".html", ".htm"}:
        markdown, image_metadata = _inject_html_images(
            source_path,
            markdown,
            work_dir,
        )

    source_name = source_path.stem
    result = {
        "ok": True,
        "protocol_version": manifest.get("protocol_version"),
        "worker_revision": manifest.get("worker_revision"),
        "job_id": manifest.get("job_id"),
        "parser_name": "mineru",
        "content_format": "markdown",
        "documents": [
            {
                "page_content": markdown,
                "metadata": {
                    "source_name": source_name,
                    "parser": "mineru",
                    "content_format": "markdown",
                    **image_metadata,
                },
            }
        ],
        "metadata": {
            "tier": manifest.get("tier"),
            **image_metadata,
        },
    }

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "markdown.md").write_text(markdown, encoding="utf-8")

    # structured_content.json 对调试有价值，体积通常可控。
    structured = mineru_dir / "structured_content.json"
    if structured.exists():
        shutil.copy2(structured, output_root / "structured_content.json")
    shutil.rmtree(work_dir, ignore_errors=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = parse_job(
        Path(args.job_root).resolve(),
        Path(args.output).resolve(),
    )
    print(json.dumps({"ok": True, "job_id": result["job_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
