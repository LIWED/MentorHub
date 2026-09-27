from __future__ import annotations

import time
import uuid
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage

from backend.agents.qa.nodes import (
    _qa_runtime,
    check_sufficiency_node,
    classify_query_node,
    gap_retrieve_node,
    gap_rewrite_node,
    hyde_generate_node,
    hyde_retrieve_node,
    iterative_plan_node,
    iterative_retrieve_node,
    merge_evidence_node,
    multi_query_rewrite_node,
    rerank_evidence_node,
    resolve_scope_node,
    rewrite_query_node,
    retrieve_node,
    structural_router_node,
)


def _evidence_preview(chunks: list[dict], limit: int = 6) -> list[dict]:
    result: list[dict] = []
    for index, chunk in enumerate(chunks[:limit], 1):
        metadata = chunk.get("metadata") or {}
        result.append(
            {
                "rank": index,
                "content": (chunk.get("content") or "")[:1200],
                "score": round(float(chunk.get("score") or 0.0), 4),
                "source_name": metadata.get("source_name") or "",
                "document_id": metadata.get("document_id") or "",
                "relative_path": metadata.get("relative_path") or "",
                "chapter": metadata.get("chapter") or "",
                "section": metadata.get("section") or "",
                "heading_path": metadata.get("heading_path") or "",
                "chunk_index": int(metadata.get("chunk_index") or 0),
                "chunk_type": metadata.get("chunk_type") or "text",
            }
        )
    return result


def _trace_summary(trace: dict) -> dict:
    return {
        "query": trace.get("query") or "",
        "elapsed_ms": trace.get("elapsed_ms") or 0.0,
        "filter_expr": trace.get("filter_expr") or "",
        "candidate_count": int(trace.get("candidate_count") or 0),
        "ranked_count": len(trace.get("ranked_docs") or []),
        "confidence": round(float(trace.get("confidence") or 0.0), 4),
        "recall_top_k": int(trace.get("recall_top_k") or 0),
        "rerank_top_k": int(trace.get("rerank_top_k") or 0),
    }


async def run_retrieval_debug_chain(
    *,
    query: str,
    tenant_id: str,
    student_id: str,
    course_id: str | None = None,
    document_id: str | None = None,
    enable_web_search: bool = False,
) -> dict:
    """
    运行与正式 QA 一致的“检索决策链”，但停在生成回答之前。

    复用正式 node；不会调用 generate_rag / generate_direct / web_search，
    也不会写聊天历史或 memory。
    """
    runtime = _qa_runtime()
    state: dict[str, Any] = {
        "messages": [HumanMessage(content=query)],
        "student_id": student_id,
        "tenant_id": tenant_id,
        "session_id": f"retrieval-debug-{uuid.uuid4().hex}",
        "course_id": course_id,
        "requested_document_id": document_id,
        "enable_web_search": enable_web_search,
        "_debug_retrieval_traces": [],
    }
    steps: list[dict] = []
    total_started = time.perf_counter()

    async def run_node(
        name: str,
        label: str,
        func: Callable[[dict], Awaitable[dict]],
        summary_builder: Callable[[dict, dict], str],
        detail_builder: Callable[[dict, dict], dict] | None = None,
    ) -> dict:
        before_trace_count = len(state.get("_debug_retrieval_traces") or [])
        started = time.perf_counter()
        result = await func(state)
        elapsed_ms = (time.perf_counter() - started) * 1000
        state.update(result or {})
        new_traces = (state.get("_debug_retrieval_traces") or [])[before_trace_count:]
        details = detail_builder(state, result or {}) if detail_builder else {}
        if new_traces:
            details["retrieval_calls"] = [_trace_summary(item) for item in new_traces]
        steps.append(
            {
                "name": name,
                "label": label,
                "elapsed_ms": round(elapsed_ms, 2),
                "summary": summary_builder(state, result or {}),
                "details": details,
            }
        )
        return result or {}

    def add_decision(name: str, label: str, summary: str, details: dict | None = None):
        steps.append(
            {
                "name": name,
                "label": label,
                "elapsed_ms": 0.0,
                "summary": summary,
                "details": details or {},
            }
        )

    await run_node(
        "classify_query",
        "问题分类",
        classify_query_node,
        lambda s, r: (
            "识别为通用问题，不进入知识库检索"
            if s.get("query_type") == "GENERAL"
            else "识别为专业问题，进入知识库检索"
        ),
        lambda s, r: {
            "query_type": s.get("query_type"),
            "original_query": s.get("original_query"),
        },
    )

    if state.get("query_type") == "GENERAL":
        general_status = (
            "would_web_fallback"
            if state.get("enable_web_search", False)
            else "general_query"
        )
        add_decision(
            "stop",
            "结束",
            (
                "通用问题且启用了 Web：正式链路下一步会联网搜索，本测试不执行 Web"
                if general_status == "would_web_fallback"
                else "通用问题：正式链路会直接生成回答，本测试不执行生成节点"
            ),
            {"status": general_status},
        )
        return _final_payload(state, steps, total_started, general_status, runtime)

    await run_node(
        "rewrite_query",
        "Query Rewrite",
        rewrite_query_node,
        lambda s, r: (
            "无历史上下文，保持原 Query"
            if s.get("rewritten_query") == s.get("original_query")
            else "结合上下文完成 Query Rewrite"
        ),
        lambda s, r: {
            "original_query": s.get("original_query"),
            "rewritten_query": s.get("rewritten_query"),
        },
    )

    await run_node(
        "resolve_scope",
        "Metadata Scope",
        resolve_scope_node,
        lambda s, r: _scope_summary(s),
        lambda s, r: {
            "metadata_scope": s.get("metadata_scope") or {},
            "scope_source": s.get("scope_source") or "",
        },
    )

    await run_node(
        "structural_router",
        "结构路由",
        structural_router_node,
        lambda s, r: f"选择 {s.get('query_type', 'SINGLE')} 检索结构",
        lambda s, r: {"strategy": s.get("query_type", "SINGLE")},
    )

    strategy = str(state.get("query_type") or "SINGLE").upper()
    if strategy == "BROAD":
        await run_node(
            "multi_query_rewrite",
            "Multi Query",
            multi_query_rewrite_node,
            lambda s, r: f"拆解为 {len(s.get('rewritten_queries') or [])} 个并行子 Query",
            lambda s, r: {"queries": s.get("rewritten_queries") or []},
        )
        initial_node = retrieve_node
        initial_name = "retrieve"
        initial_label = "BROAD 检索"
    elif strategy == "ITERATIVE":
        await run_node(
            "iterative_plan",
            "Iterative Plan",
            iterative_plan_node,
            lambda s, r: f"规划 {len(s.get('iterative_plan') or [])} 个依赖式检索问题",
            lambda s, r: {"plan": s.get("iterative_plan") or []},
        )
        initial_node = iterative_retrieve_node
        initial_name = "iterative_retrieve"
        initial_label = "迭代检索"
    else:
        initial_node = retrieve_node
        initial_name = "retrieve"
        initial_label = "SINGLE 检索"

    await run_node(
        initial_name,
        initial_label,
        initial_node,
        lambda s, r: _retrieval_summary(s, runtime.retrieval_confidence_threshold),
        lambda s, r: {
            "confidence": round(float(s.get("confidence") or 0.0), 4),
            "threshold": runtime.retrieval_confidence_threshold,
            "evidence_count": len(s.get("ranked_chunks") or []),
            "high_confidence": bool(s.get("is_high_confidence")),
        },
    )

    if not state.get("is_high_confidence", False):
        add_decision(
            "quality_gate",
            "Quality Gate",
            (
                f"Top-1 {float(state.get('confidence') or 0.0):.3f} < "
                f"{runtime.retrieval_confidence_threshold:.3f}，触发 HyDE"
            ),
            {"decision": "hyde"},
        )
        await run_node(
            "hyde_generate",
            "HyDE Generate",
            hyde_generate_node,
            lambda s, r: (
                f"生成 {len(s.get('hyde_document') or '')} 字符的假想文档"
                if s.get("hyde_document")
                else "HyDE 生成失败或为空"
            ),
            lambda s, r: {"hyde_document": s.get("hyde_document") or ""},
        )
        await run_node(
            "hyde_retrieve",
            "HyDE Retrieval",
            hyde_retrieve_node,
            lambda s, r: _retrieval_summary(
                s,
                runtime.retrieval_confidence_threshold,
                prefix="合并 Direct + HyDE 后",
            ),
            lambda s, r: {
                "confidence": round(float(s.get("confidence") or 0.0), 4),
                "threshold": runtime.retrieval_confidence_threshold,
                "evidence_count": len(s.get("ranked_chunks") or []),
                "high_confidence": bool(s.get("is_high_confidence")),
            },
        )
        if not state.get("is_high_confidence", False):
            fallback_status = (
                "would_web_fallback"
                if state.get("enable_web_search", False)
                else "would_direct_fallback"
            )
            add_decision(
                "quality_gate",
                "Quality Gate",
                (
                    f"HyDE 后仍低于阈值：{float(state.get('confidence') or 0.0):.3f} < "
                    f"{runtime.retrieval_confidence_threshold:.3f}"
                ),
                {"decision": fallback_status},
            )
            return _final_payload(
                state,
                steps,
                total_started,
                fallback_status,
                runtime,
            )
    else:
        add_decision(
            "quality_gate",
            "Quality Gate",
            (
                f"Top-1 {float(state.get('confidence') or 0.0):.3f} ≥ "
                f"{runtime.retrieval_confidence_threshold:.3f}，通过相关性门槛"
            ),
            {"decision": "sufficiency"},
        )

    while True:
        await run_node(
            "check_sufficiency",
            "Evidence Sufficiency",
            check_sufficiency_node,
            lambda s, r: (
                "证据覆盖充分，可进入 RAG 生成"
                if s.get("sufficient")
                else f"证据不足，发现 {len(s.get('missing_gaps') or [])} 个信息缺口"
            ),
            lambda s, r: {
                "sufficient": bool(s.get("sufficient")),
                "missing_gaps": s.get("missing_gaps") or [],
                "search_hints": s.get("search_hints") or [],
                "gap_round": int(s.get("gap_round") or 0),
            },
        )
        if state.get("sufficient"):
            return _final_payload(
                state,
                steps,
                total_started,
                "ready_for_rag",
                runtime,
            )

        gap_round = int(state.get("gap_round") or 0)
        max_gap_rounds = int(state.get("max_gap_rounds") or runtime.max_gap_rounds)
        if gap_round >= max_gap_rounds:
            add_decision(
                "gap_budget",
                "Gap Budget",
                f"已达到 Gap Retrieval 上限 {max_gap_rounds} 轮，停止补搜",
                {"gap_round": gap_round, "max_gap_rounds": max_gap_rounds},
            )
            final_status = (
                "would_web_fallback"
                if state.get("enable_web_search", False)
                else "ready_for_partial_rag"
            )
            return _final_payload(
                state,
                steps,
                total_started,
                final_status,
                runtime,
            )

        await run_node(
            "gap_rewrite",
            "Gap Query",
            gap_rewrite_node,
            lambda s, r: f"针对证据缺口生成 {len(s.get('gap_queries') or [])} 个补充 Query",
            lambda s, r: {"queries": s.get("gap_queries") or []},
        )
        old_count = len(state.get("evidence_pool") or state.get("ranked_chunks") or [])
        await run_node(
            "gap_retrieve",
            "Gap Retrieval",
            gap_retrieve_node,
            lambda s, r: f"第 {s.get('gap_round', 0)} 轮补搜新增 {len(s.get('new_evidence') or [])} 条证据",
            lambda s, r: {
                "gap_round": int(s.get("gap_round") or 0),
                "new_evidence_count": len(s.get("new_evidence") or []),
            },
        )
        new_count = len(state.get("new_evidence") or [])
        await run_node(
            "merge_evidence",
            "Merge Evidence",
            merge_evidence_node,
            lambda s, r: f"旧证据 {old_count} + 新证据 {new_count} → 合并后 {len(s.get('evidence_pool') or [])}",
            lambda s, r: {"evidence_pool_count": len(s.get("evidence_pool") or [])},
        )
        await run_node(
            "rerank_evidence",
            "Global Rerank",
            rerank_evidence_node,
            lambda s, r: _retrieval_summary(
                s,
                runtime.retrieval_confidence_threshold,
                prefix="累计证据全局重排后",
            ),
            lambda s, r: {
                "confidence": round(float(s.get("confidence") or 0.0), 4),
                "evidence_count": len(s.get("ranked_chunks") or []),
            },
        )


def _scope_summary(state: dict) -> str:
    scope = state.get("metadata_scope") or {}
    if scope.get("document_id"):
        return "限定到当前租户 / 课程 / 文档"
    if scope.get("course_id"):
        return "限定到当前租户 / 课程"
    return "仅使用租户隔离，全课程可检索"


def _retrieval_summary(state: dict, threshold: float, prefix: str = "") -> str:
    confidence = float(state.get("confidence") or 0.0)
    count = len(state.get("ranked_chunks") or [])
    verdict = "通过" if confidence >= threshold else "未通过"
    head = f"{prefix}：" if prefix else ""
    return f"{head}得到 {count} 条重排证据，Top-1={confidence:.3f}，{verdict} {threshold:.3f} 阈值"


def _final_payload(
    state: dict,
    steps: list[dict],
    total_started: float,
    status: str,
    runtime,
) -> dict:
    traces = state.get("_debug_retrieval_traces") or []
    return {
        "status": status,
        "strategy": str(state.get("query_type") or "GENERAL"),
        "rewritten_query": state.get("rewritten_query") or state.get("original_query") or "",
        "metadata_scope": state.get("metadata_scope") or {},
        "scope_source": state.get("scope_source") or "",
        "confidence": round(float(state.get("confidence") or 0.0), 4),
        "evidence_count": len(state.get("ranked_chunks") or []),
        "total_ms": round((time.perf_counter() - total_started) * 1000, 2),
        "steps": steps,
        "final_evidence": _evidence_preview(state.get("ranked_chunks") or []),
        "retrieval_calls": [_trace_summary(trace) for trace in traces],
        "runtime_config": {
            "recall_top_k_single": runtime.recall_top_k_single,
            "recall_top_k_hyde": runtime.recall_top_k_hyde,
            "recall_top_k_broad_per": runtime.recall_top_k_broad_per,
            "recall_top_k_iterative": runtime.recall_top_k_iterative,
            "rerank_evidence_top_k": runtime.rerank_evidence_top_k,
            "final_context_top_k": runtime.final_context_top_k,
            "retrieval_confidence_threshold": runtime.retrieval_confidence_threshold,
            "max_gap_queries": runtime.max_gap_queries,
            "max_gap_rounds": runtime.max_gap_rounds,
        },
    }
