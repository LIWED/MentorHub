"""
通过本地 Ollama 多模态模型对整张图片做语义理解。

默认使用 qwen3.5:4b，重点输出流程图 / 架构图的节点与边。
只使用 localhost Ollama，不产生外部 API 成本。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import httpx


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3.5:4b"

FLOWCHART_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "flowchart",
                "architecture",
                "pipeline",
                "chart",
                "screenshot",
                "photo",
                "other",
            ],
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["id", "text"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["source", "target", "label"],
            },
        },
    },
    "required": [
        "type",
        "title",
        "description",
        "nodes",
        "edges",
    ],
}

PROMPT = """
分析整张图片，不要把图片切成互不相关的小块。

你的目标是忠实恢复图片中的信息，特别是流程图、架构图、pipeline 和系统关系图。

要求：
1. 如果是流程图/架构图/pipeline：
   - nodes 中记录所有清晰可见的重要节点；
   - text 必须尽量保留图片中的原始节点文字；
   - edges 只记录能明确看到箭头方向的关系；
   - source/target 必须引用 nodes 中的 id；
   - 条件分支文字（如 Yes/No、成功/失败）放在 label；
   - 看不清的边不要猜；
   - 严禁使用 Node 1、Node 2 这种虚构节点文字。
2. 如果不是流程关系图，nodes 和 edges 返回空数组，并在 description 中描述图片的有效信息。
3. 不要根据常识补充图片中不存在的信息。
4. 宁可少提取一些边，也不要伪造关系。
""".strip()

FLOW_STRUCTURE_PROMPT = """
这是一张流程图、架构图或 pipeline 图。请只做“结构恢复”，不要泛泛描述。

只返回一个合法 JSON object，不要 Markdown，不要解释：
{
  "type": "flowchart",
  "title": "",
  "description": "",
  "nodes": [
    {"id": "n1", "text": "图片中真实可见的节点文字"}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "label": ""}
  ]
}

强制要求：
1. 尽可能列出图中清晰可见的主要节点，text 保留原文。
2. source/target 必须引用 nodes 的 id。
3. 只记录能明确看到箭头方向的边。
4. 箭头旁有 Yes/No、成功/失败等条件时写入 label。
5. 不允许使用 Node 1、Node 2、Step 1 之类虚构文字。
6. 看不清的边直接省略，不要猜。
7. 宁可节点多、边少，也不要伪造连线。
""".strip()

_DIAGRAM_TYPES = {"flowchart", "architecture", "pipeline"}
_DIAGRAM_DESCRIPTION_HINTS = (
    "流程图",
    "架构图",
    "架构",
    "pipeline",
    "workflow",
    "flowchart",
    "architecture",
)


def _normalize_result(value: dict[str, Any]) -> dict[str, Any]:
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
            if source not in node_ids or target not in node_ids:
                continue
            if source == target:
                continue
            edge = {
                "source": source,
                "target": target,
                "label": str(item.get("label") or "").strip(),
            }
            if edge not in edges:
                edges.append(edge)

    return {
        "type": str(value.get("type") or "other").strip().lower(),
        "title": str(value.get("title") or "").strip(),
        "description": str(value.get("description") or "").strip(),
        "nodes": nodes,
        "edges": edges,
    }


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith(fence):
            text = text.rstrip()[: -len(fence)].rstrip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError(
                f"Ollama 未返回可解析 JSON：{text[:1000]}"
            )
        value = json.loads(text[start : end + 1])

    if isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]
        if len(dict_items) == 1:
            value = dict_items[0]
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Ollama 图片分析结果不是 JSON object：{text[:500]}"
        )
    return value


def analyze_image(
    image_path: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    path = Path(image_path).resolve()
    image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    def request(client: httpx.Client, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 3072,
            },
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
        }
        response = client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        body = response.json()
        content = (
            body.get("message", {}).get("content", "")
            if isinstance(body, dict)
            else ""
        )
        if not content:
            raise RuntimeError("Ollama 没有返回图片分析内容")
        return _normalize_result(_parse_json_content(content)), body

    with httpx.Client(timeout=timeout_seconds) as client:
        result, first_body = request(client, PROMPT)

        description_lower = result["description"].lower()
        looks_like_diagram = (
            result["type"] in _DIAGRAM_TYPES
            or any(
                hint.lower() in description_lower
                for hint in _DIAGRAM_DESCRIPTION_HINTS
            )
        )
        second_body: dict[str, Any] | None = None
        if looks_like_diagram and not result["nodes"]:
            structured, second_body = request(
                client,
                FLOW_STRUCTURE_PROMPT,
            )
            if structured["nodes"]:
                structured["description"] = (
                    structured["description"]
                    or result["description"]
                )
                structured["title"] = (
                    structured["title"]
                    or result["title"]
                )
                result = structured

    result["model"] = model
    result["input"] = str(path)
    result["total_duration_ns"] = (
        (first_body.get("total_duration") or 0)
        + ((second_body or {}).get("total_duration") or 0)
    )
    result["vision_passes"] = 2 if second_body else 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    result = analyze_image(
        args.input,
        model=args.model,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
