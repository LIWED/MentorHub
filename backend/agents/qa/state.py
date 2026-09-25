# backend/agents/qa/state.py

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class QAState(TypedDict):
    """
    智能问答 Agent 的完整状态定义。
    所有节点通过读写此 State 进行数据传递。
    """

    # ── ① 消息历史（LangGraph 核心，add_messages reducer）────────
    # 节点每次返回 messages 时自动追加，不覆盖历史
    messages: Annotated[list[BaseMessage], add_messages]

    # ── ② 请求上下文（Orchestrator 注入，节点只读）───────────────
    student_id:  str            # 学员 ID
    tenant_id:   str            # 租户 ID（Milvus / DB 多租户隔离）
    session_id:  str            # 会话 ID（用于构造 thread_id）
    course_id:   Optional[str]  # 课程 ID，限制检索范围；None = 全库检索

    # ── ③ Query 处理中间结果──────────────────────────────────────
    original_query:    str         # 用户原始输入，全程不变
    rewritten_query:   str         # specialized：结合历史改写后的独立检索 Query
    query_type:        str         # GENERAL / SINGLE / BROAD / ITERATIVE
    rewritten_queries: list[str]   # BROAD 分支：Multi-Query 改写后的子 Query 列表
    hyde_document:     Optional[str]  # Direct Retrieval 低质量时生成的 HyDE 假想文档

    # ITERATIVE 分支：最多 3 个逻辑问题、最多 3 轮依赖检索
    iterative_seed_query: Optional[str]
    iterative_intent:     Optional[str]
    iterative_plan:       list[dict]
    iterative_entities:   list[str]
    iterative_queries:    list[str]
    iterative_results:    list[dict]
    iteration_count:      int

    # ── ④ 检索与精排结果─────────────────────────────────────────
    # retrieve() 内部已处理 BGE-M3 编码，State 无需存储中间向量。
    # ranked_chunks 保留较宽的精排证据窗口；最终生成时再截取更小的 Context Top-K。
    ranked_chunks:      list[dict]   # BGEReranker 精排后的 Evidence Top-K
    evidence_pool:      list[dict]   # 多轮检索累计的去重证据池
    new_evidence:       list[dict]   # 当前 Gap Retrieval 新增证据
    confidence:         float        # 精排置信度 [0, 1]
    is_high_confidence: bool         # confidence >= 0.75
    web_search_results: list[dict]   # Web Search MCP 返回结果（低置信度时填充）

    # P0：Evidence Sufficiency + Gap Retrieval
    sufficient:         bool         # 当前证据是否足够回答完整问题
    missing_gaps:       list[str]    # 当前证据缺失的关键信息
    search_hints:       list[str]    # 针对缺口的检索提示
    gap_queries:        list[str]    # 本轮实际执行的 Gap Query
    gap_round:          int          # 已完成的 Gap Retrieval 轮数
    max_gap_rounds:     int          # 最大 Gap Retrieval 轮数

    # ── ⑤ 生成结果 & 控制标记──────────────────────────────────────
    answer:            str           # 最终回答文本
    sources:           list[str]     # 来源标注列表（高置信度 RAG 时填充）
    answer_mode:       str           # "rag" / "llm_direct"
    existing_summary:  Optional[str] # 当前会话的历史摘要（从 DB 读取）
    should_summarize:  bool          # 是否触发摘要压缩
    enable_web_search: bool          # True = HyDE 后仍低置信度时允许 Web Search 兜底
    fallback_used:     bool          # 当前请求是否已触发 HyDE / 降级处理
    structured_output: Optional[dict]  # 传给 Orchestrator 的结构化数据
