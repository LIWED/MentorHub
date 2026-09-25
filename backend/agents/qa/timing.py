from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Mapping


_node_timings: ContextVar[dict[str, float] | None] = ContextVar(
    "qa_node_timings",
    default=None,
)

NODE_LABELS: dict[str, str] = {
    "classify_query": "问题分类",
    "rewrite_query": "结合上下文改写问题",
    "structural_router": "选择检索结构",
    "hyde_generate": "生成检索假设",
    "hyde_retrieve": "HyDE 二次检索与重排",
    "multi_query_rewrite": "多角度拆解问题",
    "iterative_plan": "规划迭代检索",
    "iterative_retrieve": "执行迭代检索",
    "retrieve": "知识库检索与重排",
    "check_sufficiency": "判断证据是否充分",
    "gap_rewrite": "生成缺口检索问题",
    "gap_retrieve": "补充检索缺失证据",
    "merge_evidence": "合并新旧检索证据",
    "rerank_evidence": "重新排序完整证据",
    "web_search": "联网搜索",
    "generate_rag": "基于知识库生成回答",
    "generate_direct": "生成直接回答",
    "generate_general": "生成通用回答",
    "enqueue_pending": "记录待补充知识",
    "save_memory": "保存会话记忆",
}


@contextmanager
def collect_node_timings() -> Iterator[dict[str, float]]:
    """Collect QA node timings for one request without leaking across requests."""
    timings: dict[str, float] = {}
    token = _node_timings.set(timings)
    try:
        yield timings
    finally:
        _node_timings.reset(token)


def start_node_timing_collection() -> tuple[dict[str, float], Token]:
    timings: dict[str, float] = {}
    token = _node_timings.set(timings)
    return timings, token


def stop_node_timing_collection(token: Token) -> None:
    _node_timings.reset(token)


def record_node_timing(node_name: str, elapsed_ms: float) -> None:
    timings = _node_timings.get()
    if timings is None:
        return
    timings[node_name] = timings.get(node_name, 0.0) + elapsed_ms


def build_timing_payload(
    timings: Mapping[str, float],
    *,
    total_ms: float,
    graph_ms: float,
) -> dict:
    """Build the user-facing timing payload carried by the final SSE meta event."""
    return {
        "total_ms": round(total_ms, 2),
        "graph_ms": round(graph_ms, 2),
        "nodes": [
            {
                "name": node_name,
                "label": NODE_LABELS.get(node_name, node_name.replace("_", " ")),
                "elapsed_ms": round(elapsed_ms, 2),
            }
            for node_name, elapsed_ms in timings.items()
        ],
    }
