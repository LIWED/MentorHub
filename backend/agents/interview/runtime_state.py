from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def serialize_runtime_state(state: dict[str, Any]) -> dict[str, Any]:
    """Convert InterviewState into JSON-safe data for DB persistence."""
    payload: dict[str, Any] = {}
    for key, value in state.items():
        if key == "messages":
            payload[key] = [_serialize_message(message) for message in value or []]
        else:
            payload[key] = value
    return payload


def deserialize_runtime_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Restore JSON-safe runtime data back into a LangGraph InterviewState-like dict."""
    if not payload:
        return {}

    state = dict(payload)
    state["messages"] = [
        message
        for item in payload.get("messages", [])
        if (message := _deserialize_message(item)) is not None
    ]
    return state


def _serialize_message(message: BaseMessage) -> dict[str, Any]:
    if isinstance(message, HumanMessage):
        role = "human"
    elif isinstance(message, AIMessage):
        role = "ai"
    elif isinstance(message, SystemMessage):
        role = "system"
    else:
        role = message.type or "unknown"

    return {
        "role": role,
        "content": message.content,
    }


def _deserialize_message(payload: Any) -> BaseMessage | None:
    if not isinstance(payload, dict):
        return None

    role = payload.get("role")
    content = payload.get("content", "")

    if role in {"human", "user"}:
        return HumanMessage(content=content)
    if role in {"ai", "assistant"}:
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return None
