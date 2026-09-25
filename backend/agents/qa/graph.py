# backend/agents/qa/graph.py

import time

from langgraph.graph import StateGraph, START, END

from backend.agents.qa.state import QAState
from backend.agents.qa.nodes import (
    classify_query_node,
    rewrite_query_node,
    structural_router_node,
    hyde_generate_node,
    hyde_retrieve_node,
    multi_query_rewrite_node,
    iterative_plan_node,
    iterative_retrieve_node,
    retrieve_node,
    check_sufficiency_node,
    gap_rewrite_node,
    gap_retrieve_node,
    merge_evidence_node,
    rerank_evidence_node,
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
from backend.agents.qa.timing import record_node_timing


logger = get_logger(__name__)


def _timed_node(node_name: str, node_func):
    """统一统计 LangGraph 节点耗时，避免在每个节点里重复埋点。"""
    async def wrapped(state: QAState) -> dict:
        started = time.perf_counter()
        try:
            result = await node_func(state)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            record_node_timing(node_name, elapsed_ms)
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
        record_node_timing(node_name, elapsed_ms)
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
    classify_query 之后只区分 GENERAL 与 specialized。

    specialized 不在这里决定检索策略，而是先做 Query Rewrite，
    再交给 structural_router 判断 SINGLE / BROAD / ITERATIVE。
    """
    qt = state.get("query_type", "SINGLE").upper()
    if qt == "GENERAL":
        # 明确的问候/感谢/身份等社交类输入永远直接回答，避免无意义联网搜索。
        if _rule_classify_general(state.get("original_query", "")):
            return "GENERAL"
        if state.get("enable_web_search", False):
            return "GENERAL_WEB"
        return "GENERAL"
    return "SPECIALIZED"


def _route_by_confidence(state: QAState) -> str:
    """
    Retrieval Quality Gate。

    高置信度 → 直接 RAG；
    第一次低置信度 → 先做 HyDE 二次检索；
    HyDE 后仍低置信度 → 根据联网开关进入 Web Search 或 LLM Direct。
    """
    if state.get("is_high_confidence", False):
        return "high"
    if not state.get("fallback_used", False):
        return "low_hyde"
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


def _route_after_sufficiency(state: QAState) -> str:
    """
    Evidence Sufficiency Gate。

    sufficient=True → 基于知识库回答；
    insufficient 且还有 Gap Retrieval 预算 → 只补搜缺口；
    预算耗尽 → 有 Web 则联网兜底，否则基于现有证据给出有限回答。
    """
    if state.get("sufficient", False):
        return "generate"

    gap_round = int(state.get("gap_round", 0))
    max_gap_rounds = int(state.get("max_gap_rounds", 2))
    if gap_round < max_gap_rounds:
        return "gap"

    if state.get("enable_web_search", False):
        return "web"
    return "generate_partial"


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
    builder.add_node("structural_router",    _timed_node("structural_router", structural_router_node))
    builder.add_node("hyde_generate",        _timed_node("hyde_generate", hyde_generate_node))
    builder.add_node("hyde_retrieve",        _timed_node("hyde_retrieve", hyde_retrieve_node))
    builder.add_node("multi_query_rewrite",  _timed_node("multi_query_rewrite", multi_query_rewrite_node))
    builder.add_node("iterative_plan",        _timed_node("iterative_plan", iterative_plan_node))
    builder.add_node("iterative_retrieve",    _timed_node("iterative_retrieve", iterative_retrieve_node))
    builder.add_node("retrieve",             _timed_node("retrieve", retrieve_node))
    builder.add_node("check_sufficiency",    _timed_node("check_sufficiency", check_sufficiency_node))
    builder.add_node("gap_rewrite",          _timed_node("gap_rewrite", gap_rewrite_node))
    builder.add_node("gap_retrieve",         _timed_node("gap_retrieve", gap_retrieve_node))
    builder.add_node("merge_evidence",       _timed_node("merge_evidence", merge_evidence_node))
    builder.add_node("rerank_evidence",      _timed_node("rerank_evidence", rerank_evidence_node))
    builder.add_node("generate_rag",         _timed_node("generate_rag", generate_rag_node))
    builder.add_node("web_search",            _timed_node("web_search", web_search_node))
    builder.add_node("generate_direct",       _timed_node("generate_direct", generate_direct_node))
    builder.add_node("generate_general",      _timed_node("generate_general", generate_general_node))
    builder.add_node("enqueue_pending",       _timed_node("enqueue_pending", enqueue_pending_node))
    builder.add_node("save_memory",           _timed_node("save_memory", save_memory_node))

    # ── 入口固定边 ────────────────────────────────────────────
    builder.add_edge(START, "classify_query")

    # ── 条件边①：GENERAL / specialized ───────────────────────
    builder.add_conditional_edges(
        "classify_query",
        _route_by_query_type,
        {
            "GENERAL":     "generate_general",
            "GENERAL_WEB": "web_search",
            "SPECIALIZED": "rewrite_query",
        },
    )

    # specialized 统一先 Rewrite，再判断结构路由。
    builder.add_edge("rewrite_query", "structural_router")
    builder.add_conditional_edges(
        "structural_router",
        lambda state: state.get("query_type", "SINGLE").upper(),
        {
            "SINGLE":    "retrieve",
            "BROAD":     "multi_query_rewrite",
            "ITERATIVE": "iterative_plan",
        },
    )

    builder.add_edge("multi_query_rewrite", "retrieve")
    builder.add_edge("iterative_plan",      "iterative_retrieve")

    # HyDE 是低质量检索后的 fallback，不再属于一级结构路由。
    builder.add_edge("hyde_generate", "hyde_retrieve")

    # ── 条件边②：Retrieval Quality Gate ─────────────────────
    builder.add_conditional_edges(
        "retrieve",
        _route_by_confidence,
        {
            "high":       "check_sufficiency",
            "low_hyde":   "hyde_generate",
            "low_web":    "web_search",
            "low_direct": "generate_direct",
        },
    )

    builder.add_conditional_edges(
        "iterative_retrieve",
        _route_by_confidence,
        {
            "high":       "check_sufficiency",
            "low_hyde":   "hyde_generate",
            "low_web":    "web_search",
            "low_direct": "generate_direct",
        },
    )

    # HyDE 第二次检索完成后再次经过同一个 Quality Gate。
    # hyde_generate 已将 fallback_used=True，因此不会形成 HyDE 循环。
    builder.add_conditional_edges(
        "hyde_retrieve",
        _route_by_confidence,
        {
            "high":       "check_sufficiency",
            "low_hyde":   "generate_direct",  # 安全兜底，理论上不会命中
            "low_web":    "web_search",
            "low_direct": "generate_direct",
        },
    )

    # ── 条件边③：Evidence Sufficiency + Gap Retrieval Loop ───
    builder.add_conditional_edges(
        "check_sufficiency",
        _route_after_sufficiency,
        {
            "generate":         "generate_rag",
            "gap":              "gap_rewrite",
            "web":              "web_search",
            "generate_partial": "generate_rag",
        },
    )
    builder.add_edge("gap_rewrite", "gap_retrieve")
    builder.add_edge("gap_retrieve", "merge_evidence")
    builder.add_edge("merge_evidence", "rerank_evidence")
    builder.add_edge("rerank_evidence", "check_sufficiency")

    # ── 条件边④：web_search 出口路由 ─────────────────────────
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
