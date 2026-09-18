# backend/agents/qa/graph.py

import time

from langgraph.graph import StateGraph, START, END

from backend.agents.qa.state import QAState
from backend.agents.qa.nodes import (
    classify_query_node,
    rewrite_query_node,
    hyde_generate_node,
    multi_query_rewrite_node,
    iterative_plan_node,
    iterative_retrieve_node,
    retrieve_node,
    generate_rag_node,
    web_search_node,
    generate_direct_node,
    generate_general_node,
    enqueue_pending_node,
    save_memory_node,
    _rule_classify_general,
)
from backend.core.memory import get_memory_saver
from backend.core.logger import get_logger


logger = get_logger(__name__)


def _timed_node(node_name: str, node_func):
    """统一统计 LangGraph 节点耗时，避免在每个节点里重复埋点。"""
    async def wrapped(state: QAState) -> dict:
        started = time.perf_counter()
        try:
            result = await node_func(state)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "qa.node_timing",
                node=node_name,
                elapsed_ms=round(elapsed_ms, 2),
                status="error",
                session_id=state.get("session_id"),
                query_type=state.get("query_type"),
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "qa.node_timing",
            node=node_name,
            elapsed_ms=round(elapsed_ms, 2),
            status="ok",
            session_id=state.get("session_id"),
            query_type=(result or {}).get("query_type", state.get("query_type")),
        )
        return result

    return wrapped


def _route_by_query_type(state: QAState) -> str:
    """
    classify_query 之后的路由：根据 query_type 和 enable_web_search 分流。

    GENERAL + enable_web_search=True  → "GENERAL_WEB"：先联网再回答
    GENERAL + enable_web_search=False → "GENERAL"：直接 LLM
    PRECISE / VAGUE / BROAD / ITERATIVE → 直接进对应检索分支
    """
    qt = state.get("query_type", "PRECISE").upper()
    if qt == "GENERAL":
        # 明确的问候/感谢/身份等社交类输入永远直接回答，避免无意义联网搜索。
        if _rule_classify_general(state.get("original_query", "")):
            return "GENERAL"
        if state.get("enable_web_search", False):
            return "GENERAL_WEB"
    return qt


def _route_by_confidence(state: QAState) -> str:
    """
    retrieve 之后的路由：根据置信度和联网开关分流。

    is_high_confidence=True              → "high"：RAG 高质量回答
    is_high_confidence=False
      + enable_web_search=True           → "low_web"：先联网补充再直答
      + enable_web_search=False          → "low_direct"：直接 LLM 兜底
    """
    if state.get("is_high_confidence", False):
        return "high"
    if state.get("enable_web_search", False):
        return "low_web"
    return "low_direct"


def _route_after_web_search(state: QAState) -> str:
    """
    web_search 节点被两条路径共用，走完搜索后需要区分去向：
      - 来自 GENERAL_WEB 路径（query_type=GENERAL）→ generate_general
      - 来自低置信度路径                            → generate_direct
    """
    if state.get("query_type", "").upper() == "GENERAL":
        return "generate_general"
    return "generate_direct"
def build_qa_graph():
    """
    构建并编译 QA Agent 的 LangGraph 状态图。

    Returns:
        编译后的 CompiledGraph，供 API 层和 Orchestrator 调用。
    """
    builder = StateGraph(QAState)

    # ── 注册节点 ──────────────────────────────────────────────
    builder.add_node("classify_query",       _timed_node("classify_query", classify_query_node))
    builder.add_node("rewrite_query",        _timed_node("rewrite_query", rewrite_query_node))
    builder.add_node("hyde_generate",        _timed_node("hyde_generate", hyde_generate_node))
    builder.add_node("multi_query_rewrite",  _timed_node("multi_query_rewrite", multi_query_rewrite_node))
    builder.add_node("iterative_plan",        _timed_node("iterative_plan", iterative_plan_node))
    builder.add_node("iterative_retrieve",    _timed_node("iterative_retrieve", iterative_retrieve_node))
    builder.add_node("retrieve",             _timed_node("retrieve", retrieve_node))
    builder.add_node("generate_rag",         _timed_node("generate_rag", generate_rag_node))
    builder.add_node("web_search",            _timed_node("web_search", web_search_node))
    builder.add_node("generate_direct",       _timed_node("generate_direct", generate_direct_node))
    builder.add_node("generate_general",      _timed_node("generate_general", generate_general_node))
    builder.add_node("enqueue_pending",       _timed_node("enqueue_pending", enqueue_pending_node))
    builder.add_node("save_memory",           _timed_node("save_memory", save_memory_node))

    # ── 入口固定边 ────────────────────────────────────────────
    builder.add_edge(START, "classify_query")

    # ── 条件边①：Query 类型路由 ──────────────────────────────
    builder.add_conditional_edges(
        "classify_query",
        _route_by_query_type,
        {
            "GENERAL":     "generate_general",
            "GENERAL_WEB": "web_search",
            "PRECISE":     "rewrite_query",
            "VAGUE":       "rewrite_query",
            "BROAD":       "rewrite_query",
            "ITERATIVE":   "rewrite_query",
        },
    )

    # 所有 specialized Query 先做上下文重写，再进入原有检索策略。
    builder.add_conditional_edges(
        "rewrite_query",
        lambda state: state.get("query_type", "PRECISE").upper(),
        {
            "PRECISE": "retrieve",
            "VAGUE":   "hyde_generate",
            "BROAD":   "multi_query_rewrite",
            "ITERATIVE": "iterative_plan",
        },
    )

    # VAGUE / BROAD 额外预处理完成后汇入 retrieve
    builder.add_edge("hyde_generate",       "retrieve")
    builder.add_edge("multi_query_rewrite", "retrieve")
    builder.add_edge("iterative_plan",       "iterative_retrieve")

    # ── 条件边②：置信度路由 ──────────────────────────────────
    builder.add_conditional_edges(
        "retrieve",
        _route_by_confidence,
        {
            "high":       "generate_rag",
            "low_web":    "web_search",
            "low_direct": "generate_direct",
        },
    )

    builder.add_conditional_edges(
        "iterative_retrieve",
        _route_by_confidence,
        {
            "high":       "generate_rag",
            "low_web":    "web_search",
            "low_direct": "generate_direct",
        },
    )

    # ── 条件边③：web_search 出口路由 ─────────────────────────
    builder.add_conditional_edges(
        "web_search",
        _route_after_web_search,
        {
            "generate_general": "generate_general",
            "generate_direct":  "generate_direct",
        },
    )

    # ── 固定边：各生成节点 → 收尾节点 ────────────────────────
    builder.add_edge("generate_rag",     "save_memory")
    builder.add_edge("generate_general", "save_memory")
    builder.add_edge("generate_direct",  "enqueue_pending")
    builder.add_edge("enqueue_pending",  "save_memory")
    builder.add_edge("save_memory",      END)

    # ── 编译（绑定 MemorySaver 实现多轮记忆）────────────────
    checkpointer = get_memory_saver("qa")
    return builder.compile(checkpointer=checkpointer)


if __name__ == '__main__':

    graph = build_qa_graph()
    print('图编译成功')
    print('节点列表：', list(graph.nodes.keys()))
