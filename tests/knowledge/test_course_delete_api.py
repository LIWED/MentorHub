from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.v1 import knowledge


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _FakeSession:
    def __init__(self, *, document_count: int, active_document_count: int):
        self.document_count = document_count
        self.active_document_count = active_document_count
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params):
        sql = str(statement)
        if "SELECT c.id" in sql:
            return _FakeResult(
                [
                    {
                        "id": params["course_id"],
                        "document_count": self.document_count,
                        "active_document_count": self.active_document_count,
                    }
                ]
            )
        if "DELETE FROM knowledge_courses" in sql:
            return _FakeResult([(params["course_id"],)])
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_delete_course_removes_vectors_db_and_storage(monkeypatch, tmp_path):
    sessions: list[_FakeSession] = []

    def session_factory():
        session = _FakeSession(document_count=2, active_document_count=0)
        sessions.append(session)
        return session

    vector_calls: list[tuple[str, str]] = []

    class _FakeKB:
        def delete_course_and_rebuild(self, course_id: str, tenant_id: str):
            vector_calls.append((course_id, tenant_id))

    course_root = tmp_path / "tenant-default" / "course-1"
    asset = course_root / "site" / "img" / "AI.jpg"
    asset.parent.mkdir(parents=True)
    asset.write_text("asset", encoding="utf-8")

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(knowledge, "KnowledgeBaseClient", lambda: _FakeKB())
    monkeypatch.setattr(
        knowledge,
        "get_course_upload_root",
        lambda tenant_id, course_id: course_root,
    )

    await knowledge.delete_course(
        "course-1",
        current_user={"tenant_id": "tenant-default", "role": "admin"},
    )

    assert vector_calls == [("course-1", "tenant-default")]
    assert len(sessions) == 2
    assert sessions[1].committed is True
    assert not course_root.exists()


@pytest.mark.asyncio
async def test_delete_course_rejects_when_document_is_processing(monkeypatch):
    def session_factory():
        return _FakeSession(document_count=2, active_document_count=1)

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        knowledge,
        "KnowledgeBaseClient",
        lambda: (_ for _ in ()).throw(AssertionError("vector delete must not run")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.delete_course(
            "course-1",
            current_user={"tenant_id": "tenant-default", "role": "admin"},
        )

    assert exc_info.value.status_code == 409
