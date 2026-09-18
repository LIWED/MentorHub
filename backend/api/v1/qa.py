# backend/api/v1/qa.py

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import text as sa_text

from backend.agents.qa.graph import build_qa_graph
from backend.core.memory import build_thread_id
from backend.dependencies import get_current_user, AsyncSessionLocal
from backend.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ── 请求 / 响应模型 ───────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id:        str        = Field(..., description="会话 ID")
    course_id:         str | None = Field(None, description="课程 ID（可选，限定检索范围）")
    message:           str        = Field(..., min_length=1, max_length=2000)
    enable_web_search: bool       = Field(False, description="低置信度时是否先走 Web Search 再给 LLM")


class ChatResponse(BaseModel):
    session_id:    str
    answer:        str
    answer_mode:   str        # "rag" / "web_augmented" / "llm_direct" / "general"
    confidence:    float
    sources:       list[str]
    fallback_used: bool


class SessionMessage(BaseModel):
    role:       str   # "user" / "assistant"
    content:    str
    created_at: str
    sources:    list[str] = Field(default_factory=list)
    answer_mode: str | None = None
    confidence: float | None = None


class HistoryResponse(BaseModel):
    session_id:  str
    messages:    list[SessionMessage]
    summary:     str | None
    total_turns: int


class SessionListItem(BaseModel):
    session_id:  str
    title:       str
    total_turns: int
    updated_at:  str


class SessionListResponse(BaseModel):
    items: list[SessionListItem]
    total: int


async def _ensure_qa_session(
    *, student_id: str, tenant_id: str, session_id: str, title: str | None = None
) -> str:
    """确保产品层 QA 会话存在，并返回 thread_id。"""
    thread_id = build_thread_id(student_id, session_id)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                sa_text("""
                    INSERT INTO qa_sessions
                        (id, tenant_id, student_id, thread_id, session_id, title, summary_version)
                    VALUES
                        (:id, :tenant_id, :student_id, :thread_id, :session_id, :title, 0)
                    ON CONFLICT (thread_id) DO UPDATE
                    SET session_id = EXCLUDED.session_id,
                        title = CASE
                            WHEN qa_sessions.title IS NULL OR qa_sessions.title = ''
                            THEN EXCLUDED.title
                            ELSE qa_sessions.title
                        END,
                        updated_at = NOW()
                """),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "student_id": student_id,
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "title": title,
                },
            )
    return thread_id


async def _save_qa_message(
    *,
    student_id: str,
    tenant_id: str,
    session_id: str,
    role: str,
    content: str,
    sources: list[str] | None = None,
    answer_mode: str | None = None,
    confidence: float | None = None,
) -> None:
    """把一条 QA 消息持久化到 PostgreSQL。"""
    thread_id = build_thread_id(student_id, session_id)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                sa_text("""
                    INSERT INTO qa_messages
                        (id, tenant_id, student_id, session_id, thread_id,
                         role, content, sources, answer_mode, confidence)
                    VALUES
                        (:id, :tenant_id, :student_id, :session_id, :thread_id,
                         :role, :content, CAST(:sources AS JSONB), :answer_mode, :confidence)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "student_id": student_id,
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "role": role,
                    "content": content,
                    "sources": json.dumps(sources or [], ensure_ascii=False),
                    "answer_mode": answer_mode,
                    "confidence": confidence,
                },
            )
            await db.execute(
                sa_text("UPDATE qa_sessions SET updated_at = NOW() WHERE thread_id = :tid"),
                {"tid": thread_id},
            )


async def _build_graph_input_messages(
    *,
    graph,
    config: dict,
    student_id: str,
    session_id: str,
    current_message: str,
    window_size: int = 10,
) -> list:
    """有 checkpoint 时只传本轮增量；没有时从 DB 恢复最近窗口后再继续。"""
    try:
        state = await graph.aget_state(config)
        if state and state.values and state.values.get("messages"):
            return [HumanMessage(content=current_message)]
    except Exception as e:
        logger.warning("chat.checkpoint_probe_failed", error=str(e))

    thread_id = build_thread_id(student_id, session_id)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("""
                    SELECT role, content
                    FROM qa_messages
                    WHERE thread_id = :tid AND student_id = :sid
                    ORDER BY created_at DESC, id DESC
                    LIMIT :message_limit
                """),
                {
                    "tid": thread_id,
                    "sid": student_id,
                    "message_limit": window_size * 2,
                },
            )
            rows = list(reversed(result.fetchall()))

        restored = []
        for role, content in rows:
            if role == "user":
                restored.append(HumanMessage(content=content))
            elif role == "assistant":
                restored.append(AIMessage(content=content))

        if restored:
            logger.info(
                "chat.history_rehydrated",
                session_id=session_id,
                messages=len(restored),
            )
        return restored + [HumanMessage(content=current_message)]
    except Exception as e:
        logger.warning("chat.history_rehydrate_failed", error=str(e))
        return [HumanMessage(content=current_message)]

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """智能问答：发送消息，获取 RAG 或 LLM 直答（非流式）。"""
    graph = build_qa_graph()
    thread_id = build_thread_id(current_user["user_id"], req.session_id)
    config: dict = {"configurable": {"thread_id": thread_id}}

    try:
        await _ensure_qa_session(
            student_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            session_id=req.session_id,
            title=req.message[:40],
        )
        graph_messages = await _build_graph_input_messages(
            graph=graph,
            config=config,
            student_id=current_user["user_id"],
            session_id=req.session_id,
            current_message=req.message,
        )
        await _save_qa_message(
            student_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            session_id=req.session_id,
            role="user",
            content=req.message,
        )
    except Exception as e:
        logger.warning("chat.persist_user_failed", error=str(e))
        graph_messages = [HumanMessage(content=req.message)]

    initial_state = {
        "messages": graph_messages,
        "student_id": current_user["user_id"],
        "tenant_id": current_user["tenant_id"],
        "session_id": req.session_id,
        "course_id": req.course_id,
        "query_type": "PRECISE",
        "enable_web_search": req.enable_web_search,
        "web_search_results": [],
    }

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.error("chat.invoke_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AGENT_ERROR", "message": str(e)},
        )

    try:
        await _save_qa_message(
            student_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            session_id=req.session_id,
            role="assistant",
            content=result.get("answer", ""),
            sources=result.get("sources", []),
            answer_mode=result.get("answer_mode", "llm_direct"),
            confidence=result.get("confidence", 0.0),
        )
    except Exception as e:
        logger.warning("chat.persist_assistant_failed", error=str(e))

    return ChatResponse(
        session_id=req.session_id,
        answer=result.get("answer", ""),
        answer_mode=result.get("answer_mode", "llm_direct"),
        confidence=result.get("confidence", 0.0),
        sources=result.get("sources", []),
        fallback_used=result.get("fallback_used", False),
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """智能问答流式接口（SSE），同时把用户和助手消息持久化。"""
    graph = build_qa_graph()
    thread_id = build_thread_id(current_user["user_id"], req.session_id)
    config: dict = {"configurable": {"thread_id": thread_id}}

    try:
        await _ensure_qa_session(
            student_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            session_id=req.session_id,
            title=req.message[:40],
        )
        graph_messages = await _build_graph_input_messages(
            graph=graph,
            config=config,
            student_id=current_user["user_id"],
            session_id=req.session_id,
            current_message=req.message,
        )
        await _save_qa_message(
            student_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            session_id=req.session_id,
            role="user",
            content=req.message,
        )
    except Exception as e:
        logger.warning("chat_stream.persist_user_failed", error=str(e))
        graph_messages = [HumanMessage(content=req.message)]

    initial_state = {
        "messages": graph_messages,
        "student_id": current_user["user_id"],
        "tenant_id": current_user["tenant_id"],
        "session_id": req.session_id,
        "course_id": req.course_id,
        "query_type": "PRECISE",
        "enable_web_search": req.enable_web_search,
        "web_search_results": [],
    }

    _GENERATE_NODES = {"generate_rag", "generate_direct", "generate_general"}
    _PROGRESS_LABELS = {
        "classify_query": "理解问题中...",
        "hyde_generate": "理解问题中...",
        "multi_query_rewrite": "改写查询中...",
        "retrieve": "召回相关文档...",
        "web_search": "搜索互联网...",
        "generate_general": "思考中...",
    }

    async def event_generator():
        answer_mode = "llm_direct"
        confidence = 0.0
        sources: list[str] = []
        answer_parts: list[str] = []

        try:
            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                evt = event["event"]
                node = event.get("metadata", {}).get("langgraph_node", "")

                if evt == "on_chain_start" and node in _PROGRESS_LABELS:
                    yield {
                        "data": json.dumps(
                            {"type": "progress", "stage": _PROGRESS_LABELS[node]},
                            ensure_ascii=False,
                        )
                    }
                elif evt == "on_chat_model_stream" and node in _GENERATE_NODES:
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        chunk_text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                        answer_parts.append(chunk_text)
                        yield {
                            "data": json.dumps(
                                {"type": "token", "content": chunk_text},
                                ensure_ascii=False,
                            )
                        }
                elif evt == "on_chain_end" and node in _GENERATE_NODES:
                    output = event["data"].get("output", {})
                    if isinstance(output, dict):
                        if output.get("answer_mode"):
                            answer_mode = output["answer_mode"]
                        if output.get("sources") is not None:
                            sources = output["sources"]
                        _conf = (output.get("structured_output") or {}).get("confidence")
                        if _conf is not None:
                            confidence = _conf
        except Exception as e:
            logger.error("chat_stream.error", error=str(e), exc_info=True)
            yield {
                "data": json.dumps(
                    {"type": "error", "message": "流式输出异常，请使用普通接口重试"},
                    ensure_ascii=False,
                )
            }
            return

        answer_text = "".join(answer_parts).strip()
        if answer_text:
            try:
                await _save_qa_message(
                    student_id=current_user["user_id"],
                    tenant_id=current_user["tenant_id"],
                    session_id=req.session_id,
                    role="assistant",
                    content=answer_text,
                    sources=sources,
                    answer_mode=answer_mode,
                    confidence=confidence,
                )
            except Exception as e:
                logger.warning("chat_stream.persist_assistant_failed", error=str(e))

        yield {
            "data": json.dumps(
                {
                    "type": "meta",
                    "session_id": req.session_id,
                    "answer_mode": answer_mode,
                    "confidence": confidence,
                    "sources": sources,
                },
                ensure_ascii=False,
            )
        }
        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """返回当前用户持久化的 QA 会话列表。"""
    student_id = current_user["user_id"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            sa_text("""
                SELECT s.session_id,
                       COALESCE(NULLIF(s.title, ''), '新会话') AS title,
                       COUNT(m.id) FILTER (WHERE m.role = 'user') AS total_turns,
                       s.updated_at
                FROM qa_sessions s
                LEFT JOIN qa_messages m ON m.thread_id = s.thread_id
                WHERE s.student_id = :sid AND s.session_id IS NOT NULL
                GROUP BY s.id, s.session_id, s.title, s.updated_at
                HAVING COUNT(m.id) > 0
                ORDER BY s.updated_at DESC
            """),
            {"sid": student_id},
        )
        rows = result.fetchall()

    items = [
        SessionListItem(
            session_id=row[0],
            title=row[1],
            total_turns=int(row[2] or 0),
            updated_at=row[3].isoformat() if row[3] else "",
        )
        for row in rows
    ]
    return SessionListResponse(items=items, total=len(items))


@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """从 PostgreSQL 获取完整会话历史与摘要，不再依赖 MemorySaver。"""
    student_id = current_user["user_id"]
    thread_id = build_thread_id(student_id, session_id)

    async with AsyncSessionLocal() as db:
        session_result = await db.execute(
            sa_text(
                "SELECT summary FROM qa_sessions "
                "WHERE thread_id = :tid AND student_id = :sid"
            ),
            {"tid": thread_id, "sid": student_id},
        )
        session_row = session_result.fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="会话不存在")

        msg_result = await db.execute(
            sa_text("""
                SELECT role, content, sources, answer_mode, confidence, created_at
                FROM qa_messages
                WHERE thread_id = :tid AND student_id = :sid
                ORDER BY created_at ASC, id ASC
            """),
            {"tid": thread_id, "sid": student_id},
        )
        rows = msg_result.fetchall()

    messages = [
        SessionMessage(
            role=row[0],
            content=row[1],
            sources=list(row[2] or []),
            answer_mode=row[3],
            confidence=row[4],
            created_at=row[5].isoformat() if row[5] else "",
        )
        for row in rows
    ]
    return HistoryResponse(
        session_id=session_id,
        messages=messages,
        summary=session_row[0],
        total_turns=sum(1 for m in messages if m.role == "user"),
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除当前用户的一条 QA 会话及其产品层消息历史。"""
    student_id = current_user["user_id"]
    thread_id = build_thread_id(student_id, session_id)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                sa_text("DELETE FROM qa_messages WHERE thread_id = :tid AND student_id = :sid"),
                {"tid": thread_id, "sid": student_id},
            )
            await db.execute(
                sa_text("DELETE FROM qa_sessions WHERE thread_id = :tid AND student_id = :sid"),
                {"tid": thread_id, "sid": student_id},
            )
    return None

