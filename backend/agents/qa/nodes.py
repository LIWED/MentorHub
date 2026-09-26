# backend/agents/qa/nodes.py

import asyncio
import json
import re
import uuid

from sqlalchemy import text
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from backend.agents.qa.state import QAState
from backend.agents.qa.prompts import (
    HYDE_PROMPT,
    MULTI_QUERY_REWRITE_PROMPT,
    RAG_ANSWER_PROMPT,
    DIRECT_ANSWER_PROMPT,
    GENERAL_ANSWER_PROMPT,
    RAG_STRATEGY_PROMPT,
    ITERATIVE_PLAN_PROMPT,
    ITERATIVE_EXPAND_PROMPT,
    SUFFICIENCY_PROMPT,
    GAP_REWRITE_PROMPT,
    SYSTEM_PROMPT,
)
from backend.core.llm_factory import get_llm
from backend.core.memory import (
    trim_messages_to_window,
    should_trigger_summary,
    get_summary_batch,
    compress_to_summary,
    build_thread_id,
)
from backend.config import get_settings
from backend.core.logger import get_logger
from backend.core.query_classifier import get_query_classifier
from backend.core.runtime_settings import get_runtime_settings

logger = get_logger(__name__)

# ── 检索相关常量 ───────────────────────────────────────────────
MAX_BROAD_QUERIES        = 3   # BROAD 分支最多并行的子 Query 数
MAX_ITERATIVE_QUESTIONS  = 3   # ITERATIVE：最多处理 3 个逻辑问题
MAX_ITERATIONS           = 3   # ITERATIVE：最多 3 轮依赖检索


def _qa_runtime():
    """每个节点执行时读取最新 QA 运行参数，使设置页修改无需重启即可生效。"""
    return get_runtime_settings().qa

def _get_message_content(msg) -> str:
    """统一获取消息文本（兼容 .text 属性和 .content 属性）"""
    if hasattr(msg, "text") and not callable(getattr(msg, "text", None)):
        return msg.text
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


def _format_history_for_prompt(messages: list) -> str:
    """把最近几轮对话格式化为 Prompt 可用的文本"""
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"学员：{_get_message_content(msg)}")
        elif isinstance(msg, AIMessage):
            # AI 回答截断，避免 Prompt 过长
            lines.append(f"AI：{_get_message_content(msg)[:200]}...")
    # print(f'lines: {lines}')
    return "\n".join(lines) if lines else "（无历史对话）"


_WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

def _current_datetime_str() -> str:
    """返回格式化的当前时间字符串，供注入 Prompt 使用"""
    from datetime import datetime
    now = datetime.now()
    # print(f'now: {now}')
    # print(f'now.weekday()-->{now.weekday()}')
    weekday = _WEEKDAYS_CN[now.weekday()]
    return now.strftime(f"%Y年%m月%d日 {weekday} %H:%M")

def _build_system_content(summary: str | None = None) -> str:
    """
    构建注入了当前时间的 SystemMessage 内容，所有生成节点共用。
    summary 非空时追加历史学习摘要，帮助 LLM 保持多轮上下文连贯。
    """
    content = SYSTEM_PROMPT + f"\n\n【当前时间】{_current_datetime_str()}"
    # print(f'content: {content}')
    if summary:
        content += f"\n\n【学员历史学习摘要】\n{summary}"
    return content

# ──────────────────────────────────────────────────────────────
# 联网请求自动识别
# ──────────────────────────────────────────────────────────────

_WEB_SEARCH_HINTS = (
    "联网", "联网查询", "联网搜索", "上网查", "上网搜", "网上搜",
    "搜索一下", "可以搜索", "帮我搜", "百度一下", "谷歌一下",
)

def _extract_query_and_web_flag(raw: str) -> tuple[str, bool]:
    """
    检测用户消息是否含联网请求指令。
    返回 (清洗后的问题, 是否自动启用联网)。

    联网指令部分被去除，防止被 LLM 当作问题内容处理。
    例："AI是什么，如果不知道可以联网搜索"
      → ("AI 是什么", True)
    """
    import re
    needs_web = any(h in raw for h in _WEB_SEARCH_HINTS)
    # print(f'needs_web: {needs_web}')
    if not needs_web:
        return raw, False
    # clean = re.sub(
    #     r'[，,。.？?！!\s]*(?:如果不知道|不知道的话|不清楚)?(?:你可以|可以)?'
    #     r'(?:联网|上网|网上)?(?:查询|搜索|搜一下|查一查|百度|谷歌).*$',
    #     '',
    #     raw
    # ).strip()
    clean = re.sub(
        r'[，,。.？?！!\s]*(?:如果不知道|不知道的话|不清楚|你可以)'
        r'?\s*(?:可以)?(?:联网|上网|网上)'
        r'?(?:查询|搜索|搜一下|查一查|百度|谷歌).*$',
        '',
        raw,
    ).strip()
    return (clean or raw), True

# ──────────────────────────────────────────────────────────────
# 规则集
# ──────────────────────────────────────────────────────────────

_GENERAL_EXACT = {
    "你好", "hi", "hello", "嗨", "hey",
    "谢谢", "谢谢你", "感谢", "thanks", "thank you",
    "你是谁", "你叫什么", "你叫什么名字", "你是什么",
    "你能做什么", "你有什么功能", "你能帮我做什么",
    "再见", "拜拜", "bye",
}

_GENERAL_KEYWORDS = (
    "你是谁", "你叫什么", "你能做什么", "你有什么功能",
    "介绍一下你自己", "自我介绍",
    "今天天气", "天气怎么样",
    "讲个笑话", "说个故事",
    "今天是", "今天几号", "今天是几号", "今天是星期",
    "现在是", "现在几点", "现在时间", "当前时间", "当前日期",
    "几月几号", "星期几", "是几月", "几号了", "日期是", "今天日期",
)

# 命中即确认为专业问题，跳过 MiniLM，直接进 Layer 2
_SPECIALIZED_KEYWORDS = (
    "课程", "实战", "项目", "案例", "老师", "章节",
    "作业", "课堂", "培训", "我们学的", "课程项目",
    "第几章", "第几节", "训练营",
)

_SHORT_CONTEXT_HINTS = (
    "没懂", "不懂", "不太懂", "讲讲", "解释一下",
    "啥意思", "什么意思", "看不懂",
)

_BROAD_QUERY_HINTS = (
    "全面", "整体", "系统介绍", "系统讲", "总结", "梳理", "路线",
    "对比", "区别", "全景", "整体介绍", "详细介绍",
    "多个方面", "多方面",
)


def _looks_iterative_query(query: str) -> bool:
    """规则层识别明显的前后依赖复合问题。"""
    q = query.strip().lower()
    dependency_hints = (
        "它们", "这些", "上述", "各自", "分别", "其中",
        "前者", "后者", "对应", "每个", "各个",
    )
    discovery_hints = (
        "哪些", "哪几", "有什么", "有哪些", "是什么",
        "谁", "什么", "负责", "作用", "工作",
    )
    return (
        any(hint in q for hint in dependency_hints)
        and any(hint in q for hint in discovery_hints)
    )


def _rule_classify_general(query: str) -> bool:
    """规则层：是否为闲聊/时间/打招呼类（→ GENERAL）"""
    q = query.strip().lower()
    if q in _GENERAL_EXACT:
        return True
    return any(kw in q for kw in _GENERAL_KEYWORDS)


def _rule_classify_specialized(query: str) -> bool:
    """规则层：是否含课程/项目信号词（→ 专业，跳过 MiniLM）"""
    q = query.lower()
    return any(kw in q for kw in _SPECIALIZED_KEYWORDS)

def _fast_rag_strategy(query: str) -> str:
    """规则快判结构路由：SINGLE / BROAD / ITERATIVE。"""
    q = query.strip().lower()
    if _looks_iterative_query(q):
        return "ITERATIVE"
    # 极短的“没懂/讲讲”等输入无法直接形成稳定检索意图，交给 Multi Query 展开。
    if len(q) <= 6 and any(kw in q for kw in _SHORT_CONTEXT_HINTS):
        return "BROAD"
    if any(kw in q for kw in _BROAD_QUERY_HINTS):
        return "BROAD"
    return "SINGLE"


async def _determine_rag_strategy(query: str) -> str:
    """LLM 对 BROAD / ITERATIVE 候选做结构确认；HyDE 不参与这里的分类。"""
    try:
        llm = get_llm("qa", temperature=0)
        resp = await llm.ainvoke([
            HumanMessage(content=RAG_STRATEGY_PROMPT.format(query=query))
        ])
        label = _get_message_content(resp).strip().upper()
        if label in ("SINGLE", "BROAD", "ITERATIVE"):
            return label
    except Exception as e:
        logger.warning("structural_router.strategy_failed", error=str(e))
    return "SINGLE"


async def _determine_rag_strategy_fast(query: str) -> str:
    """
    两阶段结构路由：
    ① 规则快判 SINGLE / BROAD / ITERATIVE；
    ② SINGLE 直接返回，避免常规单点问题额外调用 LLM；
    ③ BROAD / ITERATIVE 候选交给 LLM 校正结构，降低误判。
    """
    strategy = _fast_rag_strategy(query)
    if strategy == "SINGLE":
        return strategy
    return await _determine_rag_strategy(query)


# ──────────────────────────────────────────────────────────────
# 节点：classify_query — Query 类型判断（含历史摘要加载）
# ──────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────
# 节点：classify_query — Query 类型判断（含历史摘要加载）
# ──────────────────────────────────────────────────────────────

async def classify_query_node(state: QAState) -> dict:
    """
    Query 分类节点，决定走哪条处理路径。

    同时负责从 DB 加载当前会话的历史摘要（合并了源码中的 load_memory 节点）。

    这里只区分 GENERAL 与 specialized。
    specialized 先进入 Query Rewrite，再由 structural_router_node 判断：
      SINGLE / BROAD / ITERATIVE。

    HyDE 不在这里做一级分类，而是在检索质量不足时作为 fallback。
    """
    # ── 取最后一条 HumanMessage 作为原始输入 ─────────────────
    messages = state.get("messages", [])
    raw_query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            raw_query = _get_message_content(msg)
            break

    # ── 联网指令识别 ──────────────────────────────────────────
    original_query, auto_web = _extract_query_and_web_flag(raw_query)
    # print(f'original_query: {original_query}')
    # print(f'auto_web: {auto_web}')
    # ── 从 DB 加载历史摘要（取代 load_memory_and_embed_node）──
    existing_summary: str | None = None
    try:
        from backend.dependencies import AsyncSessionLocal
        thread_id = build_thread_id(state["student_id"], state["session_id"])
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT summary FROM qa_sessions WHERE thread_id = :tid"),
                {"tid": thread_id},
            )).fetchone()
            existing_summary = row[0] if row else None
    except Exception as e:
        logger.warning("classify_query.load_memory_failed", error=str(e))

    _base: dict = {
        "original_query":    original_query,
        "rewritten_query":   original_query,
        "existing_summary":  existing_summary,
        "rewritten_queries": [],
        "hyde_document":     None,
        "metadata_scope": {
            "tenant_id": state["tenant_id"],
            **({"course_id": state["course_id"]} if state.get("course_id") else {}),
        },
        "scope_source": "course" if state.get("course_id") else "tenant",
        "iterative_seed_query": None,
        "iterative_intent": None,
        "iterative_plan": [],
        "iterative_entities": [],
        "iterative_queries": [],
        "iterative_results": [],
        "iteration_count": 0,
        "ranked_chunks": [],
        "evidence_pool": [],
        "new_evidence": [],
        "sufficient": False,
        "missing_gaps": [],
        "search_hints": [],
        "gap_queries": [],
        "gap_round": 0,
        "max_gap_rounds": _qa_runtime().max_gap_rounds,
        "fallback_used": False,
    }
    if auto_web and not state.get("enable_web_search", False):
        _base["enable_web_search"] = True
        logger.info("classify_query.auto_web_enabled", query=original_query[:50])
    # print(f'_base: {_base}')
    # ── Layer 0a：规则 → GENERAL（闲聊/时间/打招呼）───────────
    if _rule_classify_general(original_query):
        logger.info("classify_query.general_by_rule", query=original_query[:50])
        return {**_base, "query_type": "GENERAL"}

        # ── Layer 0b：关键词快速通道 → 专业（课程/项目词）──────────
    if _rule_classify_specialized(original_query):
        logger.info("classify_query.specialized_by_keyword", query=original_query[:50])
        # specialized 先统一进入 Rewrite；结构策略在 Rewrite 后判断。
        return {**_base, "query_type": "SINGLE"}
    # ── Layer 1：MiniLM 二分类（CPU 推理，线程池避免阻塞）──────
    loop = asyncio.get_running_loop()
    label, confidence = await loop.run_in_executor(
        None, get_query_classifier().classify, original_query
    )

    if label == "general":
        logger.info(
            "classify_query.general_by_minilm",
            query=original_query[:50],
            confidence=round(confidence, 4),
        )
        return {**_base, "query_type": "GENERAL"}
    # ── Layer 2：MiniLM → 专业，先进入 Rewrite ─────────────────
    logger.info(
        "classify_query.specialized_by_minilm",
        query=original_query[:50],
        confidence=round(confidence, 4),
    )
    return {**_base, "query_type": "SINGLE"}


# ──────────────────────────────────────────────────────────────
# 节点：rewrite_query — specialized 多轮上下文问题重写
# ──────────────────────────────────────────────────────────────

REWRITE_HISTORY_WINDOW = 3

async def rewrite_query_node(state: QAState) -> dict:
    """
    将 specialized Query 结合最近历史改写成可独立检索的 standalone query。

    - 最近 3 轮用于解析“它/这个项目/这门课/继续”等当前指代；
    - existing_summary 仅作为较远历史的辅助背景；
    - 没有历史时直接复用 original_query，避免无意义的 LLM 调用。
    """
    original_query = state["original_query"]
    messages = state.get("messages", [])

    # 当前 HumanMessage 已在 messages 末尾，重写历史中排除它。
    history = trim_messages_to_window(
        messages[:-1], window_size=REWRITE_HISTORY_WINDOW
    )
    history_text = _format_history_for_prompt(history)
    summary = state.get("existing_summary")

    if not history:
        return {"rewritten_query": original_query}

    prompt = f"""你是 RAG 检索问题重写器。请根据对话历史，把当前问题改写为一条语义完整、脱离历史也能独立理解的检索 Query。

规则：
1. 必须解析“它、这个、该项目、这门课、上面、继续”等指代和省略信息。
2. 保留用户当前真正的提问意图，不扩展成额外问题，不回答问题。
3. 如果当前问题本身已经完整，只做必要的轻量规范化，不改变语义。
4. 只输出最终 Query，不要解释，不要加引号。

较早历史摘要（可能为空）：
{summary or '无'}

最近对话：
{history_text}

当前问题：
{original_query}

改写后的独立检索 Query："""

    try:
        llm = get_llm("qa", temperature=0)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        rewritten = _get_message_content(response).strip().strip('"“”')
        if not rewritten:
            rewritten = original_query
    except Exception as e:
        logger.warning("rewrite_query.failed", error=str(e))
        rewritten = original_query

    logger.info(
        "rewrite_query.done",
        original=original_query[:80],
        rewritten=rewritten[:120],
        history_messages=len(history),
    )
    return {"rewritten_query": rewritten}


# ──────────────────────────────────────────────────────────────
# 节点：resolve_scope — 确定 metadata 检索范围
# ──────────────────────────────────────────────────────────────

_SCOPE_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_SCOPE_CN_TOKEN_RE = re.compile(r"[一-鿿]{4,}")


def _document_match_score(query: str, filename: str, relative_path: str) -> int:
    """
    对“用户是否明确点名某个文档”做保守匹配。

    只使用文件名/相对路径中的较长中英文 token；如果多个文档并列最高分，
    调用方会放弃 soft scope，避免误过滤掉正确答案。
    """
    query_lower = (query or "").casefold()
    source = f"{filename} {relative_path}"
    tokens = {
        token.casefold()
        for token in [
            *_SCOPE_ASCII_TOKEN_RE.findall(source),
            *_SCOPE_CN_TOKEN_RE.findall(source),
        ]
    }
    score = 0
    for token in tokens:
        if token in query_lower:
            score += min(len(token), 12)
    return score


async def resolve_scope_node(state: QAState) -> dict:
    """
    生成本轮统一 metadata_scope。

    Hard scope:
      - tenant_id 永远保留；
      - 前端传入的 course_id 永远保留；
      - 显式 document_id 校验归属后保留。

    Soft scope:
      - 仅在已选择 course_id 时，根据 rewritten_query 对课程文档名做唯一命中。
      - 不确定或目录查询失败就不加 document filter。
    """
    from backend.dependencies import AsyncSessionLocal

    tenant_id = state["tenant_id"]
    course_id = state.get("course_id")
    requested_document_id = state.get("requested_document_id")
    query = state.get("rewritten_query") or state["original_query"]

    scope: dict = {"tenant_id": tenant_id}
    if course_id:
        scope["course_id"] = course_id
    source = "course" if course_id else "tenant"

    try:
        async with AsyncSessionLocal() as db:
            if requested_document_id:
                sql = """
                    SELECT id
                    FROM knowledge_documents
                    WHERE id = :document_id
                      AND tenant_id = :tenant_id
                      AND status = 'completed'
                """
                params = {
                    "document_id": requested_document_id,
                    "tenant_id": tenant_id,
                }
                if course_id:
                    sql += " AND course_id = :course_id"
                    params["course_id"] = course_id
                row = (await db.execute(text(sql), params)).first()
                if row:
                    scope["document_id"] = str(row[0])
                    source = "request_document"
                else:
                    logger.warning(
                        "resolve_scope.requested_document_invalid",
                        document_id=requested_document_id,
                        course_id=course_id,
                    )

            elif course_id:
                result = await db.execute(
                    text(
                        """
                        SELECT id, filename, relative_path
                        FROM knowledge_documents
                        WHERE tenant_id = :tenant_id
                          AND course_id = :course_id
                          AND status = 'completed'
                        ORDER BY relative_path ASC
                        """
                    ),
                    {"tenant_id": tenant_id, "course_id": course_id},
                )
                candidates = []
                for row in result.mappings().all():
                    score = _document_match_score(
                        query,
                        row["filename"],
                        row["relative_path"],
                    )
                    if score > 0:
                        candidates.append(
                            (score, str(row["id"]), row["relative_path"])
                        )

                candidates.sort(key=lambda item: item[0], reverse=True)
                if candidates and (
                    len(candidates) == 1 or candidates[0][0] > candidates[1][0]
                ):
                    scope["document_id"] = candidates[0][1]
                    source = "query_document"
                    logger.info(
                        "resolve_scope.soft_document_match",
                        document_id=candidates[0][1],
                        relative_path=candidates[0][2],
                        score=candidates[0][0],
                    )
    except Exception as exc:
        # Scope Resolver 是检索优化节点，不应因目录 DB 短暂异常打断整条 QA。
        # tenant/course hard scope 仍然保留，document soft scope 直接跳过。
        logger.warning(
            "resolve_scope.catalog_failed",
            course_id=course_id,
            error=str(exc),
        )

    logger.info(
        "resolve_scope.done",
        source=source,
        course_id=scope.get("course_id"),
        document_id=scope.get("document_id"),
    )
    return {
        "metadata_scope": scope,
        "scope_source": source,
    }

def _relax_soft_document_scope(
    scope: dict,
    scope_source: str,
) -> tuple[dict, str, bool]:
    """只有 Query 自动推断的 document scope 才允许在 0 召回时放宽。"""
    if scope_source != "query_document" or not scope.get("document_id"):
        return scope, scope_source, False
    relaxed = dict(scope)
    relaxed.pop("document_id", None)
    return relaxed, "soft_document_relaxed", True


async def _retrieve_queries_with_scope(
    state: QAState,
    queries: list[str],
    *,
    recall_top_k: int,
    rerank_top_k: int,
) -> tuple[list[tuple[str, list, float]], dict, str]:
    """
    对一组 Query 使用同一个 scope 检索。

    若 soft document scope 下所有 Query 都 0 召回，则整组统一放宽到
    tenant/course hard scope 后重试，避免 BROAD/ITERATIVE 混用不同范围。
    """
    from backend.core.reranker import retrieve

    tenant_id = state["tenant_id"]
    course_id = state.get("course_id")
    scope = dict(state.get("metadata_scope") or {})
    if not scope:
        scope = {"tenant_id": tenant_id}
        if course_id:
            scope["course_id"] = course_id
    scope_source = state.get("scope_source") or (
        "course" if course_id else "tenant"
    )
    loop = asyncio.get_running_loop()

    async def run(current_scope: dict):
        async def retrieve_one(search_query: str):
            docs, confidence = await loop.run_in_executor(
                None,
                lambda: retrieve(
                    search_query,
                    tenant_id,
                    course_id,
                    metadata_scope=current_scope,
                    recall_top_k=recall_top_k,
                    rerank_top_k=rerank_top_k,
                ),
            )
            return search_query, docs, confidence

        return await asyncio.gather(*[
            retrieve_one(search_query)
            for search_query in queries
        ]) if queries else []

    results = await run(scope)
    if results and all(not docs for _, docs, _ in results):
        relaxed_scope, relaxed_source, relaxed = _relax_soft_document_scope(
            scope,
            scope_source,
        )
        if relaxed:
            logger.info(
                "metadata_scope.soft_document_relaxed",
                document_id=scope.get("document_id"),
                course_id=scope.get("course_id"),
            )
            scope = relaxed_scope
            scope_source = relaxed_source
            results = await run(scope)

    return results, scope, scope_source


# ──────────────────────────────────────────────────────────────
# 节点：structural_router — Rewrite 后判断检索结构
# ──────────────────────────────────────────────────────────────

async def structural_router_node(state: QAState) -> dict:
    """
    只判断检索结构：SINGLE / BROAD / ITERATIVE。

    HyDE 不属于结构路由；它由后续 Retrieval Quality Gate 决定是否触发。
    """
    query = state.get("rewritten_query") or state["original_query"]
    strategy = await _determine_rag_strategy_fast(query)
    logger.info(
        "structural_router.done",
        query=query[:100],
        strategy=strategy,
    )
    return {"query_type": strategy}


# ──────────────────────────────────────────────────────────────
# 节点：hyde_generate — 低质量检索后的 HyDE fallback
# ──────────────────────────────────────────────────────────────

async def hyde_generate_node(state: QAState) -> dict:
    """
    Direct Retrieval 质量不足时，把 Query 转换为更接近知识库文档表达的
    hypothetical document，再进行第二次检索。

    该节点只负责生成 HyDE 文本；真正的二次检索由 hyde_retrieve_node 完成。
    """
    query    = state.get("rewritten_query") or state["original_query"]
    messages = state.get("messages", [])

    history_text = _format_history_for_prompt(messages[-6:])  # 最近 3 轮

    prompt = HYDE_PROMPT.format(history=history_text, query=query)

    try:
        llm = get_llm("qa", temperature=0.3)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        hyde_doc = _get_message_content(response).strip()
    except Exception as e:
        # HyDE 是增强 fallback，不应因为生成失败把整条问答链路打断。
        logger.warning("hyde_generate.failed", error=str(e))
        return {"hyde_document": "", "fallback_used": True}

    logger.info(
        "hyde_generate.done",
        query=query[:100],
        hyde_doc_length=len(hyde_doc),
        hyde_document=hyde_doc,
    )

    return {"hyde_document": hyde_doc, "fallback_used": True}

# ──────────────────────────────────────────────────────────────
# 节点：multi_query_rewrite — Multi-Query 改写（BROAD 分支）
# ──────────────────────────────────────────────────────────────

async def multi_query_rewrite_node(state: QAState) -> dict:
    """
    针对宽泛/极短 Query，改写为 3-5 个具体子 Query，
    下一节 retrieve_node 会对这些子 Query 并行检索后合并去重。
    """
    query    = state.get("rewritten_query") or state["original_query"]
    messages = state.get("messages", [])

    # 取上一轮 AI 回答（推断"没懂"指的是什么）
    last_ai_text = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_text = _get_message_content(msg)
            break

    prompt = MULTI_QUERY_REWRITE_PROMPT.format(
        last_answer=last_ai_text[:500] if last_ai_text else "（无上一轮回答）",
        query=query,
    )

    llm = get_llm("qa", temperature=0.3)
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    # 解析：每行一个子 Query，去掉序号前缀（"1. " "①" "- " 等）
    raw = _get_message_content(response).strip()
    print(f'raw: {raw}')
    rewritten = [line.lstrip("0123456789.-）)、 ").strip()
                 for line in raw.split("\n") if line.strip() and len(line.strip()) > 3][:MAX_BROAD_QUERIES]

    if not rewritten:
        rewritten = [query]   # 改写失败时回退到原始 Query

    logger.info(
        "multi_query_rewrite.done",
        original=query,
        count=len(rewritten),
        queries=rewritten,
    )

    return {"rewritten_queries": rewritten}


# ──────────────────────────────────────────────────────────────
# 节点：iterative_plan / iterative_retrieve — 依赖式多轮检索
# ──────────────────────────────────────────────────────────────

def _parse_json_object(raw: str) -> dict:
    """从 LLM 文本中提取第一个 JSON object。"""
    text_value = raw.strip()
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM output does not contain a JSON object")
    value = json.loads(text_value[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM JSON root must be an object")
    return value


def _normalize_iterative_plan(data: dict, fallback_query: str) -> list[dict]:
    """限制最多 3 个问题，并清洗 id / depends_on，避免非法依赖或循环。"""
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list):
        raw_questions = []

    plan: list[dict] = []
    valid_ids: set[str] = set()
    for index, item in enumerate(raw_questions[:MAX_ITERATIVE_QUESTIONS], 1):
        if not isinstance(item, dict):
            continue
        qid = f"q{len(plan) + 1}"
        query = str(item.get("query") or item.get("intent") or "").strip()
        intent = str(item.get("intent") or query).strip()
        if not query:
            continue

        raw_deps = item.get("depends_on") or []
        if not isinstance(raw_deps, list):
            raw_deps = []
        deps = [str(dep) for dep in raw_deps if str(dep) in valid_ids]
        if not plan:
            deps = []

        plan.append({
            "id": qid,
            "query": query,
            "intent": intent,
            "depends_on": deps,
        })
        valid_ids.add(qid)

    if not plan:
        plan = [{
            "id": "q1",
            "query": fallback_query,
            "intent": fallback_query,
            "depends_on": [],
        }]
    return plan


def _format_iterative_evidence(
    evidence_by_id: dict[str, list],
    question_ids: list[str] | None = None,
    *,
    max_docs_per_question: int = 3,
) -> str:
    """把上一轮检索证据（含文件名 metadata）整理给 Query Expansion / Sufficiency。"""
    ids = question_ids or list(evidence_by_id.keys())
    parts: list[str] = []
    for qid in ids:
        docs = evidence_by_id.get(qid, [])
        if not docs:
            parts.append(f"[{qid}] 无有效检索证据")
            continue
        for idx, doc in enumerate(docs[:max_docs_per_question], 1):
            source = (doc.metadata or {}).get("source_name", "课程文档")
            parts.append(
                f"[{qid}-证据{idx}] 来源：{source}\n"
                f"{doc.content[:700]}"
            )
    return "\n\n".join(parts) if parts else "无有效检索证据"


async def iterative_plan_node(state: QAState) -> dict:
    """为 ITERATIVE Query 生成最多 3 个带依赖关系的逻辑问题。"""
    query = state.get("rewritten_query") or state["original_query"]
    try:
        llm = get_llm("qa", temperature=0)
        response = await llm.ainvoke([
            HumanMessage(content=ITERATIVE_PLAN_PROMPT.format(query=query))
        ])
        plan = _normalize_iterative_plan(
            _parse_json_object(_get_message_content(response)),
            query,
        )
    except Exception as e:
        logger.warning("iterative_plan.failed", error=str(e))
        plan = _normalize_iterative_plan({}, query)

    seed_query = plan[0]["query"]
    dependent_intent = "；".join(
        item["intent"] for item in plan[1:]
    ) or None

    logger.info(
        "iterative_plan.done",
        questions=len(plan),
        plan=plan,
    )
    return {
        "iterative_seed_query": seed_query,
        "iterative_intent": dependent_intent,
        "iterative_plan": plan,
        "iterative_entities": [],
        "iterative_queries": [],
        "iterative_results": [],
        "iteration_count": 0,
    }


async def _expand_iterative_question(question: dict, dependency_evidence: str) -> tuple[list[str], list[str]]:
    """根据依赖证据，把一个逻辑问题展开成最多 3 个可直接检索的 Query。"""
    if not question.get("depends_on"):
        return [], [question["query"]]

    try:
        llm = get_llm("qa", temperature=0)
        response = await llm.ainvoke([
            HumanMessage(content=ITERATIVE_EXPAND_PROMPT.format(
                query=question["query"],
                intent=question["intent"],
                evidence=dependency_evidence,
            ))
        ])
        data = _parse_json_object(_get_message_content(response))
        entities = [
            str(item).strip()
            for item in (data.get("entities") or [])
            if str(item).strip()
        ][:MAX_ITERATIVE_QUESTIONS]
        queries = [
            str(item).strip()
            for item in (data.get("queries") or [])
            if str(item).strip()
        ][:MAX_ITERATIVE_QUESTIONS]
        if queries:
            return entities, queries
    except Exception as e:
        logger.warning(
            "iterative_expand.failed",
            question_id=question.get("id"),
            error=str(e),
        )

    return [], [question["query"]]


async def iterative_retrieve_node(state: QAState) -> dict:
    """
    执行受控 Iterative Retrieval：
    - 最多 3 个逻辑问题；
    - 最多 3 轮；
    - 同一依赖层并行检索；
    - 后续 Query 只基于前轮证据展开。
    """
    plan = (state.get("iterative_plan") or [])[:MAX_ITERATIVE_QUESTIONS]
    if not plan:
        plan = _normalize_iterative_plan(
            {},
            state.get("rewritten_query") or state["original_query"],
        )

    retrieval_state = dict(state)

    completed: set[str] = set()
    evidence_by_id: dict[str, list] = {}
    search_queries_by_id: dict[str, list[str]] = {}
    all_entities: list[str] = []
    all_queries: list[str] = []
    iteration_count = 0

    while len(completed) < len(plan) and iteration_count < MAX_ITERATIONS:
        ready = [
            question for question in plan
            if question["id"] not in completed
            and all(dep in completed for dep in question.get("depends_on", []))
        ]
        if not ready:
            logger.warning(
                "iterative_retrieve.no_ready_question",
                completed=sorted(completed),
                plan=plan,
            )
            break

        iteration_count += 1

        expansion_tasks = []
        for question in ready:
            dependency_evidence = _format_iterative_evidence(
                evidence_by_id,
                question.get("depends_on", []),
            )
            expansion_tasks.append(
                _expand_iterative_question(question, dependency_evidence)
            )
        expanded = await asyncio.gather(*expansion_tasks)

        retrieval_jobs: list[tuple[str, str]] = []
        for question, (entities, queries) in zip(ready, expanded):
            qid = question["id"]
            search_queries_by_id[qid] = queries
            for entity in entities:
                if entity not in all_entities:
                    all_entities.append(entity)
            for search_query in queries:
                if search_query not in all_queries:
                    all_queries.append(search_query)
                retrieval_jobs.append((qid, search_query))

        scoped_results, resolved_scope, resolved_source = (
            await _retrieve_queries_with_scope(
                retrieval_state,
                [search_query for _, search_query in retrieval_jobs],
                recall_top_k=_qa_runtime().recall_top_k_iterative,
                rerank_top_k=_qa_runtime().rerank_evidence_top_k,
            )
        )
        retrieval_state["metadata_scope"] = resolved_scope
        retrieval_state["scope_source"] = resolved_source
        retrieved = [
            (qid, docs)
            for (qid, _), (_, docs, _) in zip(retrieval_jobs, scoped_results)
        ]

        for qid, docs in retrieved:
            current = evidence_by_id.setdefault(qid, [])
            seen = {doc.content[:160] for doc in current}
            for doc in docs:
                key = doc.content[:160]
                if key not in seen:
                    current.append(doc)
                    seen.add(key)
            current.sort(key=lambda doc: doc.score, reverse=True)

        completed.update(question["id"] for question in ready)
        logger.info(
            "iterative_retrieve.iteration_done",
            iteration=iteration_count,
            questions=[q["id"] for q in ready],
            completed=sorted(completed),
        )

    # 每个逻辑问题优先保留自己的 Top-2，避免最终上下文被 seed 文档完全占满。
    final_docs = []
    seen_final: set[str] = set()
    for question in plan:
        for doc in evidence_by_id.get(question["id"], [])[:2]:
            key = doc.content[:160]
            if key not in seen_final:
                final_docs.append(doc)
                seen_final.add(key)

    ranked_chunks = [
        {
            "content": doc.content,
            "score": doc.score,
            "metadata": doc.metadata,
        }
        for doc in final_docs[:MAX_ITERATIVE_QUESTIONS * 2]
    ]

    question_scores = [
        evidence_by_id[question["id"]][0].score
        if evidence_by_id.get(question["id"]) else 0.0
        for question in plan
    ]
    confidence = (
        sum(question_scores) / len(question_scores)
        if question_scores else 0.0
    )

    # 这里只做相关性质量判断；“证据是否足够回答完整问题”统一交给
    # check_sufficiency_node，避免 Iterative 分支存在第二套 Sufficiency 逻辑。
    is_high_confidence = bool(ranked_chunks) and (
        confidence >= _qa_runtime().retrieval_confidence_threshold
    )

    iterative_results = [
        {
            "id": question["id"],
            "intent": question["intent"],
            "depends_on": question.get("depends_on", []),
            "queries": search_queries_by_id.get(question["id"], []),
            "evidence_count": len(evidence_by_id.get(question["id"], [])),
            "top_score": (
                evidence_by_id[question["id"]][0].score
                if evidence_by_id.get(question["id"]) else 0.0
            ),
        }
        for question in plan
    ]

    logger.info(
        "iterative_retrieve.done",
        iterations=iteration_count,
        questions=len(plan),
        entities=all_entities,
        queries=all_queries,
        confidence=round(confidence, 4),
        is_high_confidence=is_high_confidence,
    )
    return {
        "ranked_chunks": ranked_chunks,
        "evidence_pool": ranked_chunks,
        "new_evidence": [],
        "confidence": confidence,
        "is_high_confidence": is_high_confidence,
        "iterative_entities": all_entities,
        "iterative_queries": all_queries,
        "iterative_results": iterative_results,
        "iteration_count": iteration_count,
        "metadata_scope": retrieval_state.get("metadata_scope", {}),
        "scope_source": retrieval_state.get(
            "scope_source",
            state.get("scope_source", ""),
        ),
    }


# ──────────────────────────────────────────────────────────────
# 节点：retrieve — 混合召回 + 精排
# ──────────────────────────────────────────────────────────────

async def retrieve_node(state: QAState) -> dict:
    """
    第一阶段 Direct Retrieval。

    SINGLE → 直接使用 rewritten_query 检索；
    BROAD  → 多个子 Query 并行检索并合并去重。

    HyDE 不在这里作为一级分支；只有本次检索质量不足时才由图路由到
    hyde_generate → hyde_retrieve 做第二次增强检索。
    """
    from backend.core.reranker import BGEReranker, RankedDocument

    query_type      = state.get("query_type", "SINGLE").upper()
    original_query  = state["original_query"]
    rewritten_query = state.get("rewritten_query") or original_query

    loop = asyncio.get_running_loop()
    resolved_scope = dict(state.get("metadata_scope") or {})
    resolved_source = state.get("scope_source") or ""

    # ── BROAD：并行多 Query 检索，合并去重 ───────────────────────
    if query_type == "BROAD" and state.get("rewritten_queries"):
        broad_queries = state["rewritten_queries"][:MAX_BROAD_QUERIES]

        scoped_results, resolved_scope, resolved_source = (
            await _retrieve_queries_with_scope(
                state,
                broad_queries,
                recall_top_k=_qa_runtime().recall_top_k_broad_per,
                rerank_top_k=_qa_runtime().rerank_evidence_top_k,
            )
        )
        results = [
            (docs, confidence)
            for _, docs, confidence in scoped_results
        ]

        # 合并去重：content 前 100 字符为 key，同一内容保留最高分。
        seen: dict[str, RankedDocument] = {}
        for ranked_docs, _ in results:
            for doc in ranked_docs:
                key = doc.content[:100]
                if key not in seen or doc.score > seen[key].score:
                    seen[key] = doc

        # 不直接比较不同 sub-query 下的 CrossEncoder 分数。
        # 先合并各路候选，再用用户完整 Query 做一次全局精排。
        broad_candidates = [
            {
                "content": doc.content,
                "metadata": doc.metadata,
            }
            for doc in seen.values()
        ]
        if broad_candidates:
            reranker = BGEReranker.get_instance()
            merged, _ = await loop.run_in_executor(
                None,
                lambda: reranker.rerank_with_confidence(
                    rewritten_query,
                    broad_candidates,
                    top_k=_qa_runtime().rerank_evidence_top_k,
                ),
            )
        else:
            merged = []
    else:
        # SINGLE 以及其他安全兜底情况都先走原 Query / Rewrite Query 的直接检索。
        scoped_results, resolved_scope, resolved_source = (
            await _retrieve_queries_with_scope(
                state,
                [rewritten_query],
                recall_top_k=_qa_runtime().recall_top_k_single,
                rerank_top_k=_qa_runtime().rerank_evidence_top_k,
            )
        )
        merged = scoped_results[0][1] if scoped_results else []

    ranked_chunks = [
        {
            "content": doc.content,
            "score": doc.score,
            "metadata": doc.metadata,
        }
        for doc in merged
    ]

    confidence = ranked_chunks[0]["score"] if ranked_chunks else 0.0
    is_high_confidence = confidence >= _qa_runtime().retrieval_confidence_threshold

    logger.info(
        "retrieve.done",
        query_type=query_type,
        retrieval_query=rewritten_query[:100],
        ranked=len(ranked_chunks),
        confidence=round(confidence, 4),
        is_high_confidence=is_high_confidence,
    )

    return {
        "ranked_chunks": ranked_chunks,
        "evidence_pool": ranked_chunks,
        "new_evidence": [],
        "confidence": confidence,
        "is_high_confidence": is_high_confidence,
        "metadata_scope": resolved_scope,
        "scope_source": resolved_source,
    }


async def hyde_retrieve_node(state: QAState) -> dict:
    """
    第二阶段 HyDE Retrieval。

    复用现有 retrieve()：
    1. 使用 hypothetical document 做第二次检索；
    2. 与第一次 Direct Retrieval 的结果合并去重；
    3. 再使用真实 rewritten_query 做一次最终 Rerank；
    4. 输出新的 Top-3 和置信度，供第二次 Quality Gate 判断。
    """
    from backend.core.reranker import BGEReranker

    hyde_document = (state.get("hyde_document") or "").strip()
    if not hyde_document:
        logger.info("hyde_retrieve.skipped", reason="empty_hyde_document")
        return {
            "is_high_confidence": False,
            "fallback_used": True,
        }

    original_query  = state["original_query"]
    rewritten_query = state.get("rewritten_query") or original_query
    loop = asyncio.get_running_loop()

    scoped_results, resolved_scope, resolved_source = (
        await _retrieve_queries_with_scope(
            state,
            [hyde_document],
            recall_top_k=_qa_runtime().recall_top_k_hyde,
            rerank_top_k=_qa_runtime().rerank_evidence_top_k,
        )
    )
    hyde_docs = scoped_results[0][1] if scoped_results else []

    # 第一次 Direct Retrieval + HyDE Retrieval 合并去重。
    evidence_pool: list[dict] = []
    seen: set[str] = set()

    for chunk in state.get("evidence_pool") or state.get("ranked_chunks", []):
        content = chunk.get("content", "")
        key = content[:160]
        if content and key not in seen:
            evidence_pool.append({
                "content": content,
                "score": chunk.get("score", 0.0),
                "metadata": chunk.get("metadata", {}),
            })
            seen.add(key)

    for doc in hyde_docs:
        key = doc.content[:160]
        if doc.content and key not in seen:
            evidence_pool.append({
                "content": doc.content,
                "score": doc.score,
                "metadata": doc.metadata,
            })
            seen.add(key)

    if not evidence_pool:
        return {
            "ranked_chunks": [],
            "evidence_pool": [],
            "new_evidence": [],
            "confidence": 0.0,
            "is_high_confidence": False,
            "fallback_used": True,
            "metadata_scope": resolved_scope,
            "scope_source": resolved_source,
        }

    # HyDE 只负责扩大召回；最终排序重新回到真实 Query，降低假想答案偏移风险。
    reranker = BGEReranker.get_instance()
    final_docs, confidence = await loop.run_in_executor(
        None,
        lambda: reranker.rerank_with_confidence(
            rewritten_query,
            evidence_pool,
            top_k=_qa_runtime().rerank_evidence_top_k,
        ),
    )

    ranked_chunks = [
        {
            "content": doc.content,
            "score": doc.score,
            "metadata": doc.metadata,
        }
        for doc in final_docs
    ]
    is_high_confidence = confidence >= _qa_runtime().retrieval_confidence_threshold

    logger.info(
        "hyde_retrieve.done",
        query_type=state.get("query_type"),
        direct_candidates=len(state.get("ranked_chunks", [])),
        hyde_candidates=len(hyde_docs),
        merged_candidates=len(evidence_pool),
        ranked=len(ranked_chunks),
        confidence=round(confidence, 4),
        is_high_confidence=is_high_confidence,
    )

    return {
        "ranked_chunks": ranked_chunks,
        "evidence_pool": evidence_pool,
        "new_evidence": [],
        "confidence": confidence,
        "is_high_confidence": is_high_confidence,
        "fallback_used": True,
        "metadata_scope": resolved_scope,
        "scope_source": resolved_source,
    }


# ──────────────────────────────────────────────────────────────
# P0：Evidence Sufficiency + Gap Retrieval
# ──────────────────────────────────────────────────────────────

def _chunk_identity(chunk: dict) -> str:
    """优先用 document_id + chunk_index 去重；缺失时退回文本前缀。"""
    metadata = chunk.get("metadata") or {}
    document_id = metadata.get("document_id")
    chunk_index = metadata.get("chunk_index")
    if document_id not in (None, "") and chunk_index is not None:
        return f"{document_id}:{chunk_index}"
    return (chunk.get("content") or "")[:240]


def _format_sufficiency_evidence(chunks: list[dict]) -> str:
    """压缩 Evidence，避免 Sufficiency Judge 被过长上下文淹没。"""
    if not chunks:
        return "（无检索证据）"

    parts: list[str] = []
    for idx, chunk in enumerate(chunks[:_qa_runtime().rerank_evidence_top_k], 1):
        metadata = chunk.get("metadata") or {}
        source = metadata.get("source_name") or "课程文档"
        score = float(chunk.get("score") or 0.0)
        content = (chunk.get("content") or "")[:1200]
        parts.append(
            f"【证据{idx}｜source={source}｜score={score:.4f}】\n{content}"
        )
    return "\n\n".join(parts)


def _normalize_string_list(value, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text_value = str(item).strip()
        if text_value and text_value not in normalized:
            normalized.append(text_value)
        if len(normalized) >= limit:
            break
    return normalized


async def check_sufficiency_node(state: QAState) -> dict:
    """
    判断“相关证据是否足够回答完整问题”。

    注意：这不是相关性判断。相关性仍由 BGE Reranker + 0.75 阈值负责；
    本节点只检查 Evidence Coverage，并输出缺口供下一轮定向检索。
    """
    ranked_chunks = state.get("ranked_chunks") or []
    query = state["original_query"]
    retrieval_query = state.get("rewritten_query") or query

    if not ranked_chunks:
        return {
            "sufficient": False,
            "missing_gaps": ["当前没有可用于回答问题的知识库证据"],
            "search_hints": [retrieval_query],
        }

    try:
        llm = get_llm("qa", temperature=0)
        response = await llm.ainvoke([
            HumanMessage(content=SUFFICIENCY_PROMPT.format(
                query=query,
                retrieval_query=retrieval_query,
                evidence=_format_sufficiency_evidence(ranked_chunks),
            ))
        ])
        data = _parse_json_object(_get_message_content(response))

        raw_sufficient = data.get("sufficient", False)
        sufficient = (
            raw_sufficient
            if isinstance(raw_sufficient, bool)
            else str(raw_sufficient).strip().lower() in {"true", "yes", "sufficient"}
        )
        missing_gaps = _normalize_string_list(
            data.get("missing_gaps"),
            limit=_qa_runtime().max_gap_queries,
        )
        search_hints = _normalize_string_list(
            data.get("search_hints"),
            limit=_qa_runtime().max_gap_queries,
        )

        if sufficient:
            missing_gaps = []
            search_hints = []
        elif not missing_gaps:
            missing_gaps = ["当前证据未完整覆盖用户问题的主要信息需求"]

        logger.info(
            "sufficiency.done",
            sufficient=sufficient,
            evidence_count=len(ranked_chunks),
            missing_gaps=missing_gaps,
            gap_round=state.get("gap_round", 0),
        )
        return {
            "sufficient": sufficient,
            "missing_gaps": missing_gaps,
            "search_hints": search_hints,
        }
    except Exception as e:
        # Judge 本身失败时采用 fail-open：沿用已通过相关性 Gate 的证据，
        # 避免外部 LLM/JSON 波动把原本可用的 RAG 链路阻断。
        logger.warning("sufficiency.failed", error=str(e))
        return {
            "sufficient": bool(state.get("is_high_confidence", False)),
            "missing_gaps": [],
            "search_hints": [],
        }


async def gap_rewrite_node(state: QAState) -> dict:
    """只针对 Sufficiency Judge 指出的缺口生成最多 2 个补充检索 Query。"""
    query = state["original_query"]
    missing_gaps = state.get("missing_gaps") or []
    search_hints = state.get("search_hints") or []

    try:
        llm = get_llm("qa", temperature=0)
        response = await llm.ainvoke([
            HumanMessage(content=GAP_REWRITE_PROMPT.format(
                query=query,
                missing_gaps=json.dumps(missing_gaps, ensure_ascii=False),
                search_hints=json.dumps(search_hints, ensure_ascii=False),
            ))
        ])
        data = _parse_json_object(_get_message_content(response))
        gap_queries = _normalize_string_list(
            data.get("queries"),
            limit=_qa_runtime().max_gap_queries,
        )
    except Exception as e:
        logger.warning("gap_rewrite.failed", error=str(e))
        gap_queries = []

    if not gap_queries:
        gap_queries = _normalize_string_list(
            [*search_hints, *missing_gaps],
            limit=_qa_runtime().max_gap_queries,
        )
    if not gap_queries:
        gap_queries = [state.get("rewritten_query") or query]

    logger.info(
        "gap_rewrite.done",
        gap_round=state.get("gap_round", 0) + 1,
        queries=gap_queries,
    )
    return {"gap_queries": gap_queries}


async def gap_retrieve_node(state: QAState) -> dict:
    """复用现有 Hybrid Retrieval，对缺口 Query 做定向补充召回。"""
    gap_queries = (state.get("gap_queries") or [])[:_qa_runtime().max_gap_queries]
    next_round = int(state.get("gap_round", 0)) + 1

    scoped_results, resolved_scope, resolved_source = (
        await _retrieve_queries_with_scope(
            state,
            gap_queries,
            recall_top_k=_qa_runtime().recall_top_k_single,
            rerank_top_k=_qa_runtime().rerank_evidence_top_k,
        )
    )
    results = [
        (search_query, docs)
        for search_query, docs, _ in scoped_results
    ]

    seen: set[str] = set()
    new_evidence: list[dict] = []
    for search_query, docs in results:
        for doc in docs:
            chunk = {
                "content": doc.content,
                "score": doc.score,
                "metadata": doc.metadata,
                "trigger_query": search_query,
                "retrieval_round": next_round,
            }
            key = _chunk_identity(chunk)
            if key and key not in seen:
                new_evidence.append(chunk)
                seen.add(key)

    logger.info(
        "gap_retrieve.done",
        gap_round=next_round,
        queries=gap_queries,
        new_evidence=len(new_evidence),
    )
    return {
        "new_evidence": new_evidence,
        "gap_round": next_round,
        "metadata_scope": resolved_scope,
        "scope_source": resolved_source,
    }


async def merge_evidence_node(state: QAState) -> dict:
    """把旧 Evidence 与 Gap Retrieval 新证据合并去重，保留完整证据池。"""
    old_evidence = state.get("evidence_pool") or state.get("ranked_chunks") or []
    new_evidence = state.get("new_evidence") or []

    merged_by_key: dict[str, dict] = {}
    order: list[str] = []
    for chunk in [*old_evidence, *new_evidence]:
        key = _chunk_identity(chunk)
        if not key:
            continue
        if key not in merged_by_key:
            merged_by_key[key] = chunk
            order.append(key)
        elif float(chunk.get("score") or 0.0) > float(
            merged_by_key[key].get("score") or 0.0
        ):
            # 这里只用于同一 Chunk 去重；随后还会用原始 Query 做全局 Rerank。
            merged_by_key[key] = chunk

    evidence_pool = [merged_by_key[key] for key in order]
    logger.info(
        "merge_evidence.done",
        old=len(old_evidence),
        new=len(new_evidence),
        merged=len(evidence_pool),
    )
    return {
        "evidence_pool": evidence_pool,
        "new_evidence": [],
    }


async def rerank_evidence_node(state: QAState) -> dict:
    """用真实用户 Query 对累计 Evidence Pool 做全局重排。"""
    from backend.core.reranker import BGEReranker

    evidence_pool = state.get("evidence_pool") or []
    if not evidence_pool:
        return {
            "ranked_chunks": [],
            "confidence": 0.0,
            "is_high_confidence": False,
        }

    query = state.get("rewritten_query") or state["original_query"]
    loop = asyncio.get_running_loop()
    reranker = BGEReranker.get_instance()
    docs, confidence = await loop.run_in_executor(
        None,
        lambda: reranker.rerank_with_confidence(
            query,
            evidence_pool,
            top_k=_qa_runtime().rerank_evidence_top_k,
        ),
    )
    ranked_chunks = [
        {
            "content": doc.content,
            "score": doc.score,
            "metadata": doc.metadata,
        }
        for doc in docs
    ]
    is_high_confidence = bool(ranked_chunks) and (
        confidence >= _qa_runtime().retrieval_confidence_threshold
    )

    logger.info(
        "rerank_evidence.done",
        evidence_pool=len(evidence_pool),
        ranked=len(ranked_chunks),
        confidence=round(confidence, 4),
        is_high_confidence=is_high_confidence,
    )
    return {
        "ranked_chunks": ranked_chunks,
        "confidence": confidence,
        "is_high_confidence": is_high_confidence,
    }

# ──────────────────────────────────────────────────────────────
# 节点：generate_rag — 高置信度 RAG 生成
# ──────────────────────────────────────────────────────────────

async def generate_rag_node(state: QAState) -> dict:
    """
    高置信度 RAG 生成节点。

    将精排后的 Top-3 文档拼成 context，让 LLM 严格基于知识库内容回答。
    回答末尾附加 📚 参考来源，支持历史摘要注入保持多轮连贯性。
    """
    # Sufficiency 判断可以看更宽的 Top-6 证据窗口；真正生成时只保留
    # Final Context Top-K，减少噪音和上下文成本。
    ranked_chunks = (state.get("ranked_chunks") or [])[:_qa_runtime().final_context_top_k]
    query         = state["original_query"]
    messages      = state.get("messages", [])
    summary       = state.get("existing_summary")

    # 构建知识库上下文与来源列表
    context_parts = []
    sources = []
    for i, chunk in enumerate(ranked_chunks, 1):
        context_parts.append(f"【参考{i}】\n{chunk['content']}")
        source_name = chunk.get("metadata", {}).get("source_name", "课程文档")
        if source_name not in sources:
            sources.append(source_name)

    context_text = "\n\n".join(context_parts)

    # 消息列表：SystemMessage（含当前时间 + 历史摘要）
    llm_messages = [SystemMessage(content=_build_system_content(summary))]

    # 注入历史对话窗口（排除最后一条 HumanMessage）
    # 最后一条 HumanMessage 已拼入 RAG_ANSWER_PROMPT 的 {query}，
    # 再传一次会让问题在上下文里出现两次，影响生成质量。
    windowed = trim_messages_to_window(messages[:-1], window_size=10)
    for msg in windowed:
        if not isinstance(msg, SystemMessage):
            llm_messages.append(msg)

    rag_prompt = RAG_ANSWER_PROMPT.format(context=context_text, query=query)
    llm_messages.append(HumanMessage(content=rag_prompt))

    llm = get_llm("qa", streaming=True)
    response = await llm.ainvoke(llm_messages)
    answer_text = _get_message_content(response).strip()

    sources_text = "\n".join([f"  • {s}" for s in sources])
    final_answer = f"{answer_text}\n\n📚 **参考来源**\n{sources_text}"

    logger.info(
        "generate_rag.done",
        answer_length=len(final_answer),
        sources=sources,
        confidence=round(state.get("confidence", 0), 4),
    )

    return {
        "answer":      final_answer,
        "sources":     sources,
        "answer_mode": "rag",
        "messages":    [AIMessage(content=final_answer)],
        "should_summarize": should_trigger_summary(
            messages + [AIMessage(content=final_answer)], threshold=10, window_size=10
        ),
        "structured_output": {
            "answer":      final_answer,
            "sources":     sources,
            "confidence":  state.get("confidence", 0),
            "answer_mode": "rag",
        },
    }


# ──────────────────────────────────────────────────────────────
# 节点：web_search — Web 搜索补充（低置信度分支）
# ──────────────────────────────────────────────────────────────

async def web_search_node(state: QAState) -> dict:
    """
    低置信度分支的 Web 搜索节点。

    知识库置信度不足时，调用 Web Search MCP Server 补充互联网信息。
    MCP Server 不可用时静默降级，返回空列表，不阻断后续生成节点。
    """
    from backend.mcp.client import call_mcp_tool

    settings = get_settings()

    if not settings.web_search_mcp_url:
        return {"web_search_results": []}

    try:
        results = await call_mcp_tool(
            server_url=settings.web_search_mcp_url,
            tool_name="web_search",
            arguments={
                "query": (
                    state["original_query"]
                    if state.get("query_type", "").upper() == "GENERAL"
                    else state.get("rewritten_query") or state["original_query"]
                ),
                "max_results": 3,
            },
            timeout=10.0,
        )
        count = len(results or [])
        logger.info("web_search.done", count=count)
        return {"web_search_results": results or []}
    except Exception as e:
        logger.warning("web_search.failed", error=str(e))
        return {"web_search_results": []}


# ──────────────────────────────────────────────────────────────
# 节点：generate_direct — 低置信度 LLM 直答（含 Web 搜索补充）
# ──────────────────────────────────────────────────────────────

async def generate_direct_node(state: QAState) -> dict:
    """
    低置信度 LLM 直答节点。

    知识库无足够相关内容时，直接用 LLM 参数知识回答。
    有 Web 搜索结果时注入为上下文（web_augmented 模式）；
    无搜索结果时在回答末尾追加 ⚠️ 提示（llm_direct 模式）。
    """
    query    = state["original_query"]
    messages = state.get("messages", [])
    summary  = state.get("existing_summary")

    llm_messages = [SystemMessage(content=_build_system_content(summary))]

    windowed = trim_messages_to_window(messages[:-1], window_size=10)
    for msg in windowed:
        if not isinstance(msg, SystemMessage):
            llm_messages.append(msg)

    # ── Web 搜索结果注入 ──────────────────────────────────────
    web_results = state.get("web_search_results") or []
    # print(f'web_results-->{web_results}')
    web_context = ""
    web_sources: list[str] = []
    if web_results:
        snippets = "\n".join(
            f"  [{i + 1}] {r.get('title', '')}（{r.get('url', '')}）\n {r.get('snippet', '')[:300]}"
            for i, r in enumerate(web_results)
        )
        web_context = f"\n\n【Web 搜索补充参考】\n{snippets}"
        web_sources = [r.get("url", "") for r in web_results if r.get("url")]
    # print(f'web_context-->{web_context}')
    # print(f'web_sources-->{web_sources}')
    #
    direct_prompt = DIRECT_ANSWER_PROMPT.format(query=query) + web_context
    llm_messages.append(HumanMessage(content=direct_prompt))

    llm = get_llm("qa", streaming=True)
    response = await llm.ainvoke(llm_messages)
    answer_text = _get_message_content(response).strip()
    # print(f'answer_text-->{answer_text}')

    if web_sources:
        # URL 通过 sources 字段传给前端，由 UI 折叠面板展示，不拼进正文
        final_answer = answer_text
        answer_mode  = "web_augmented"
    else:
        final_answer = (
            f"{answer_text}\n\n"
            f"⚠️ **说明**：以上为 AI 基于通用知识的回答，课程知识库中暂无相关内容。"
            f"建议以教师讲解为准，或联系教师补充相关资料。"
        )
        answer_mode = "llm_direct"

    logger.info(
        "generate_direct.done",
        answer_length=len(final_answer),
        confidence=round(state.get("confidence", 0), 4),
        web_sources=len(web_sources),
    )

    return {
        "answer":      final_answer,
        "sources":     web_sources,
        "answer_mode": answer_mode,
        "messages":    [AIMessage(content=final_answer)],
        "should_summarize": should_trigger_summary(
            messages + [AIMessage(content=final_answer)], threshold=10, window_size=10
        ),
        "structured_output": {
            "answer":      final_answer,
            "sources":     web_sources,
            "confidence":  state.get("confidence", 0),
            "answer_mode": answer_mode,
        },
    }


# ──────────────────────────────────────────────────────────────
# 节点：generate_general — 通用问题直答（跳过 RAG）
# ──────────────────────────────────────────────────────────────

async def generate_general_node(state: QAState) -> dict:
    """
    通用问题直答节点（query_type=GENERAL）。

    适用于：打招呼、问时间、闲聊等与课程无关的问题。
    联网模式下若 web_search_results 非空，注入搜索结果提供时效性信息。
    """
    query       = state["original_query"]
    messages    = state.get("messages", [])
    web_results = state.get("web_search_results") or []

    web_context = ""
    web_sources: list[str] = []
    if web_results:
        snippets = "\n".join(
            f"  [{i + 1}] {r.get('title', '')}（{r.get('url', '')}）\n"
            f"      {r.get('snippet', '')[:300]}"
            for i, r in enumerate(web_results)
        )
        web_context = f"【Web 搜索结果】\n{snippets}\n\n"
        web_sources = [r.get("url", "") for r in web_results if r.get("url")]

    history_text = _format_history_for_prompt(messages[-6:])
    prompt = GENERAL_ANSWER_PROMPT.format(
        query=query,
        history=history_text,
        current_time=_current_datetime_str(),
        web_context=web_context,
    )
    # print(f'prompt: {prompt}')
    # print("*"*80)
    llm = get_llm("qa", streaming=True)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    answer_text = _get_message_content(response).strip()

    answer_mode = "web_augmented" if web_sources else "general"
    # print(f'answer_text: {answer_text}')
    # print("*" * 80)
    logger.info(
        "generate_general.done",
        answer_length=len(answer_text),
        web_sources=len(web_sources),
    )

    return {
        "answer":      answer_text,
        "sources":     web_sources,
        "answer_mode": answer_mode,
        "messages":    [AIMessage(content=answer_text)],
        "should_summarize": should_trigger_summary(
            messages + [AIMessage(content=answer_text)], threshold=10, window_size=10
        ),
        "structured_output": {
            "answer":      answer_text,
            "sources":     web_sources,
            "confidence":  1.0,
            "answer_mode": answer_mode,
        },
    }
# ──────────────────────────────────────────────────────────────
# 节点：enqueue_pending — 低置信度问题入队（纯副作用）
# ──────────────────────────────────────────────────────────────

async def enqueue_pending_node(state: QAState) -> dict:
    """
    将低置信度问题写入 knowledge_pending_queue，供教师审查补充知识库。

    ON CONFLICT DO NOTHING：幂等写入，同一问题重复触发不会产生重复记录。
    失败静默，不影响已生成的回答。返回 {} 不修改 State。
    """
    from backend.dependencies import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO knowledge_pending_queue
                            (id, tenant_id, question, student_id, confidence, status)
                        VALUES (:id, :tenant_id, :question, :student_id, :confidence, 'pending')
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "id":         str(uuid.uuid4()),
                        "tenant_id":  state["tenant_id"],
                        "question":   state["original_query"],
                        "student_id": state["student_id"],
                        "confidence": state.get("confidence", 0.0),
                    },
                )
        logger.info(
            "enqueue_pending.done",
            question=state["original_query"][:50],
            confidence=state.get("confidence", 0),
        )
    except Exception as e:
        logger.warning("enqueue_pending.failed", error=str(e))

    return {}

# ──────────────────────────────────────────────────────────────
# 节点：save_memory — 记忆保存（纯副作用）
# ──────────────────────────────────────────────────────────────

async def save_memory_node(state: QAState) -> dict:
    """
    记忆保存节点：条件触发摘要压缩 + 写回 qa_sessions 表。

    should_summarize=True 时，仅把最近 10 轮滑动窗口之外新累计的 10 轮
    历史增量合并进旧摘要，再写回数据库。失败静默，不中断主流程。
    """
    from backend.dependencies import AsyncSessionLocal

    messages   = state.get("messages", [])
    student_id = state["student_id"]
    session_id = state["session_id"]
    tenant_id  = state["tenant_id"]
    thread_id  = build_thread_id(student_id, session_id)
    summary    = state.get("existing_summary")

    summary_changed = False

    # ── 条件触发增量摘要：只压缩最近 10 轮滑动窗口之外的新一批旧消息 ──
    if state.get("should_summarize", False):
        msgs_to_compress = get_summary_batch(
            messages, threshold=10, window_size=10
        )

        if msgs_to_compress:
            try:
                summary = await compress_to_summary(
                    messages=msgs_to_compress,
                    existing_summary=summary,
                )
                summary_changed = True
                logger.info(
                    "save_memory.summary_compressed",
                    thread_id=thread_id,
                    compressed_messages=len(msgs_to_compress),
                )
            except Exception as e:
                logger.warning("save_memory.compress_failed", error=str(e))

    # ── qa_sessions 每轮都确保存在；摘要版本只在真正生成新摘要时递增 ──
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO qa_sessions
                            (id, tenant_id, student_id, thread_id, session_id, summary_version)
                        VALUES (:id, :tenant_id, :student_id, :thread_id, :session_id, 0)
                        ON CONFLICT (thread_id) DO UPDATE
                            SET session_id = COALESCE(qa_sessions.session_id, EXCLUDED.session_id),
                                updated_at = NOW()
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "student_id": student_id,
                        "thread_id": thread_id,
                        "session_id": session_id,
                    },
                )

                if summary_changed:
                    await session.execute(
                        text("""
                            UPDATE qa_sessions
                            SET summary = :summary,
                                summary_version = summary_version + 1,
                                updated_at = NOW()
                            WHERE thread_id = :thread_id
                        """),
                        {"summary": summary, "thread_id": thread_id},
                    )
    except Exception as e:
        logger.warning("save_memory.db_write_failed", error=str(e))

    return {}


if __name__ == '__main__':
    # messages = [SystemMessage(content="你是一个专家"),
    #             HumanMessage(content="你是谁"),
    #             AIMessage(content="我叫张三")]
    #
    # print(_format_history_for_prompt(messages))
    # print(_current_datetime_str())
    # _build_system_content()
    # print(_extract_query_and_web_flag(raw="什么是AI, 如果不知道可以联网搜索"))
    # print(_rule_classify_general(query="你好"))
    # print(_rule_classify_specialized(query="AI课程怎么样"))
    # print(_fast_rag_strategy(query="全面的帮我概括下"))
    import asyncio
    # print(asyncio.run(_determine_rag_strategy(query="Transformer模型的架构组成部分是什么")))
    # 测试下规则下：判断问题为GENERAL
    # state = {"messages": [HumanMessage(content="模型训练的时候是怎么计算梯度的"),
    #                       AIMessage(content="反向传播的算法")],
    #          "original_query":"给我概括下",
    #          "student_id":"stu_001",
    #          "session_id":"sess_001"}
    # result = asyncio.run(classify_query_node(state))
    # result = asyncio.run(hyde_generate_node(state))
    # result = asyncio.run(multi_query_rewrite_node(state))
    # print(f'result: {result}')
    # results = asyncio.run(retrieve_node(state))
    # state.update(results)
    # results2 = asyncio.run(generate_rag_node(state))
    # print(results2)
    # 一定开启mcp server服务（new_main.py运行）
    # results3 = asyncio.run(web_search_node(state))
    # # print(f'results3={results3}')
    # state = {"query_type":"SINGLE",
    #          "original_query":"什么是AI",
    #          "tenant_id":"tenant_default",}
    # #
    # web_search_results = {'web_search_results': [{'title': '人工智能',
    #                                              'url': 'https:www.123.com',
    #                                              'snippet': '人工智能',
    #                                              'content': '人工智能（AI）让机器像人一样智能，代替人类工作'}]}
    # state.update(web_search_results)
    # # results4 = asyncio.run(generate_direct_node(state))
    # # print(results4)
    # results5 = asyncio.run(generate_general_node(state))
    # print(results5)
    # state = {"query_type": "SINGLE",
    #          "original_query": "什么是AI",
    #          "tenant_id": "tenant_default", }
    # # state.update(web_search_results)
    # state = {"query_type": "SINGLE",
    #          "original_query": "AI和JAVA有什么区别和联系",
    #          "tenant_id": "tenant_default",
    #          "student_id":"1efe1246-e355-4714-8b1b-bd4e7c8bce51", #必须在users库中出现
    #          "confidence": 0.74}
    #
    # asyncio.run(enqueue_pending_node(state))
    state = {"messages": [HumanMessage(content="模型训练的时候是怎么计算梯度的"),
                          AIMessage(content="反向传播的算法")],
             "original_query": "给我概括下",
             "student_id":"1efe1246-e355-4714-8b1b-bd4e7c8bce51",
             "tenant_id": "tenant_default",
             "session_id": "sess_001",
             "existing_summary":"这是我们给大家演示的最最新的摘要"}
    result5 = asyncio.run(save_memory_node(state))
    print("*"*80)
    print(result5)


