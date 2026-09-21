from __future__ import annotations

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import backend.api.v1.interview as interview_api
from backend.agents.interview.runtime_state import (
    deserialize_runtime_state,
    serialize_runtime_state,
)


def test_serialize_interview_messages_hides_internal_start_message():
    messages = [
        HumanMessage(content="[开始面试]"),
        AIMessage(content="你好，请先做一下自我介绍。"),
        HumanMessage(content="我是小明，主要做 Python 和 RAG。"),
        SystemMessage(content="内部系统提示"),
        AIMessage(content="请介绍一下你做过的 RAG 项目。"),
    ]

    history = interview_api._serialize_interview_messages(messages)

    assert [item.model_dump() for item in history] == [
        {"role": "assistant", "content": "你好，请先做一下自我介绍。"},
        {"role": "user", "content": "我是小明，主要做 Python 和 RAG。"},
        {"role": "assistant", "content": "请介绍一下你做过的 RAG 项目。"},
    ]


def test_runtime_state_round_trip_restores_langchain_messages():
    state = {
        "current_stage": "project",
        "total_turn_count": 4,
        "messages": [
            HumanMessage(content="[开始面试]"),
            AIMessage(content="开场白"),
            HumanMessage(content="我的回答"),
        ],
        "question_bank": [{"id": "q1", "content": "什么是 RAG？", "asked": True}],
    }

    restored = deserialize_runtime_state(serialize_runtime_state(state))

    assert restored["current_stage"] == "project"
    assert restored["total_turn_count"] == 4
    assert isinstance(restored["messages"][0], HumanMessage)
    assert isinstance(restored["messages"][1], AIMessage)
    assert restored["messages"][2].content == "我的回答"
    assert restored["question_bank"] == state["question_bank"]


@pytest.mark.asyncio
async def test_get_session_history_uses_existing_memory_state(monkeypatch):
    class FakeMappings:
        def fetchone(self):
            return {"status": "in_progress", "runtime_state": None}

    class FakeResult:
        def mappings(self):
            return FakeMappings()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            return FakeResult()

    class FakeSnapshot:
        values = {
            "current_stage": "project",
            "total_turn_count": 4,
            "messages": [
                HumanMessage(content="[开始面试]"),
                AIMessage(content="开场白"),
                HumanMessage(content="我的回答"),
                AIMessage(content="下一题"),
            ],
        }

    class FakeGraph:
        async def aget_state(self, _config):
            return FakeSnapshot()

        async def aupdate_state(self, *_args, **_kwargs):
            raise AssertionError("existing MemorySaver state should not be overwritten")

    monkeypatch.setattr(interview_api, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(interview_api, "_graph", FakeGraph())

    response = await interview_api.get_session_history(
        "session-1",
        current_user={"user_id": "student-1", "tenant_id": "tenant-1"},
    )

    assert response.status == "in_progress"
    assert response.current_stage == "project"
    assert response.total_turns == 4
    assert [item.model_dump() for item in response.messages] == [
        {"role": "assistant", "content": "开场白"},
        {"role": "user", "content": "我的回答"},
        {"role": "assistant", "content": "下一题"},
    ]


@pytest.mark.asyncio
async def test_get_session_history_restores_persisted_runtime_state(monkeypatch):
    persisted = serialize_runtime_state(
        {
            "current_stage": "tech_base",
            "total_turn_count": 3,
            "messages": [
                HumanMessage(content="[开始面试]"),
                AIMessage(content="开场白"),
                HumanMessage(content="自我介绍"),
                AIMessage(content="第一道技术题"),
            ],
        }
    )

    class FakeMappings:
        def fetchone(self):
            return {"status": "in_progress", "runtime_state": persisted}

    class FakeResult:
        def mappings(self):
            return FakeMappings()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            return FakeResult()

    class EmptySnapshot:
        values = {}

    class FakeGraph:
        def __init__(self):
            self.restored = None

        async def aget_state(self, _config):
            return EmptySnapshot()

        async def aupdate_state(self, _config, values):
            self.restored = values

    graph = FakeGraph()
    monkeypatch.setattr(interview_api, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(interview_api, "_graph", graph)

    response = await interview_api.get_session_history(
        "session-1",
        current_user={"user_id": "student-1", "tenant_id": "tenant-1"},
    )

    assert graph.restored is not None
    assert graph.restored["current_stage"] == "tech_base"
    assert response.current_stage == "tech_base"
    assert response.total_turns == 3
    assert [item.model_dump() for item in response.messages] == [
        {"role": "assistant", "content": "开场白"},
        {"role": "user", "content": "自我介绍"},
        {"role": "assistant", "content": "第一道技术题"},
    ]


@pytest.mark.asyncio
async def test_get_session_history_rejects_legacy_session_without_any_state(monkeypatch):
    class FakeMappings:
        def fetchone(self):
            return {"status": "in_progress", "runtime_state": None}

    class FakeResult:
        def mappings(self):
            return FakeMappings()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            return FakeResult()

    class EmptySnapshot:
        values = {}

    class FakeGraph:
        async def aget_state(self, _config):
            return EmptySnapshot()

        async def aupdate_state(self, *_args, **_kwargs):
            raise AssertionError("no persisted state should not hydrate")

    monkeypatch.setattr(interview_api, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(interview_api, "_graph", FakeGraph())

    with pytest.raises(HTTPException) as exc:
        await interview_api.get_session_history(
            "session-1",
            current_user={"user_id": "student-1", "tenant_id": "tenant-1"},
        )

    assert exc.value.status_code == 409
