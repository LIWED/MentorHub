"""
使用 MinerU 自带 VLM 对整张图片做语义理解。

与 mineru_parse_worker.py 不同：
- parse worker 负责 OCR / layout / table / formula 等文档解析；
- 本 worker 不切块，直接把整张原图交给 VLM；
- 重点解决流程图、架构图、管线图在切块后丢失节点关系的问题。

输出 JSON 到 stdout。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image


IMAGE_UNDERSTANDING_PROMPT = """
Analyze the entire image as one visual object.

Return ONLY one valid JSON object, with no Markdown fences and no extra text.

Schema:
{
  "type": "flowchart|architecture|pipeline|chart|screenshot|photo|other",
  "title": "visible title or empty string",
  "description": "concise factual description in Chinese",
  "nodes": [
    {"id": "n1", "text": "exact visible node text"}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "label": "visible edge/condition label or empty string"}
  ]
}

Rules:
1. Inspect the WHOLE image. Do not split it into independent crops.
2. For flowcharts / architecture / pipeline diagrams:
   - preserve visible node text exactly;
   - preserve arrow direction;
   - preserve visible branch labels such as Yes/No, true/false;
   - use nodes[].id only as internal identifiers;
   - NEVER use placeholder node text such as "Node 1", "Node 2", "Step 1";
   - do not invent an edge when the arrow direction is unclear;
   - omit uncertain edges rather than guessing.
3. For non-diagram images, nodes and edges must be empty arrays.
4. Do not infer hidden information that is not visually supported.
5. Prefer an incomplete but faithful structure over a complete but fabricated one.
""".strip()


def _extract_json(text: str) -> dict[str, Any]:
    content = text.strip()
    fence = chr(96) * 3
    if content.startswith(fence):
        first_newline = content.find("\n")
        if first_newline >= 0:
            content = content[first_newline + 1 :]
        if content.rstrip().endswith(fence):
            content = content.rstrip()[: -len(fence)].rstrip()

    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"VLM 未返回 JSON：{content[:1000]}")
        value = json.loads(content[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("VLM 返回结果不是 JSON object")
    return value


def _normalize_result(value: dict[str, Any]) -> dict[str, Any]:
    image_type = str(value.get("type") or "other").strip().lower()
    allowed_types = {
        "flowchart",
        "architecture",
        "pipeline",
        "chart",
        "screenshot",
        "photo",
        "other",
    }
    if image_type not in allowed_types:
        image_type = "other"

    raw_nodes = value.get("nodes")
    raw_edges = value.get("edges")
    nodes: list[dict[str, str]] = []
    node_ids: set[str] = set()

    if isinstance(raw_nodes, list):
        for index, item in enumerate(raw_nodes, start=1):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id") or f"n{index}").strip()
            node_text = str(item.get("text") or "").strip()
            if not node_text:
                continue
            if re.fullmatch(
                r"(?:node|step)\s*\d+",
                node_text,
                flags=re.IGNORECASE,
            ):
                continue
            if node_id in node_ids:
                node_id = f"n{index}"
            node_ids.add(node_id)
            nodes.append({"id": node_id, "text": node_text})

    edges: list[dict[str, str]] = []
    if isinstance(raw_edges, list):
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if (
                source not in node_ids
                or target not in node_ids
                or source == target
            ):
                continue
            edge = {
                "source": source,
                "target": target,
                "label": str(item.get("label") or "").strip(),
            }
            if edge not in edges:
                edges.append(edge)

    return {
        "type": image_type,
        "title": str(value.get("title") or "").strip(),
        "description": str(value.get("description") or "").strip(),
        "nodes": nodes,
        "edges": edges,
    }


def _predict(image_path: Path) -> tuple[str, str]:
    from mineru.model.vlm.client import get_vlm_predictor
    from mineru_vl_utils.vlm_client.base_client import SamplingParams

    predictor, backend = get_vlm_predictor()
    image = Image.open(image_path).convert("RGB")
    params = SamplingParams(
        temperature=0.1,
        top_p=0.9,
        max_new_tokens=3072,
    )

    raw_client = getattr(predictor, "client", None)
    if raw_client is not None:
        return (
            raw_client.predict(
                image,
                prompt=IMAGE_UNDERSTANDING_PROMPT,
                sampling_params=params,
            ),
            backend,
        )

    if hasattr(predictor, "_call") and hasattr(predictor, "_predictor"):
        return (
            predictor._call(
                lambda: predictor._predictor.client.aio_predict(
                    image,
                    prompt=IMAGE_UNDERSTANDING_PROMPT,
                    sampling_params=params,
                )
            ),
            backend,
        )

    raise RuntimeError(
        f"不支持的 MinerU VLM predictor：{type(predictor)!r}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    image_path = Path(args.input).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    raw_text, backend = _predict(image_path)
    result = _normalize_result(_extract_json(raw_text))
    result["backend"] = backend
    result["input"] = str(image_path)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
