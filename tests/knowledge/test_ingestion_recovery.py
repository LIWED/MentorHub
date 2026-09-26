from __future__ import annotations

import pytest

from backend.api.v1 import knowledge


class _RecoveryResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _RecoverySession:
    def __init__(self, stale_rows, queued_rows):
        self._stale_rows = stale_rows
        self._queued_rows = queued_rows
        self.executed_sql: list[str] = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)
        if "UPDATE knowledge_documents" in sql and "status = 'uploaded'" in sql:
            return _RecoveryResult(self._stale_rows)
        if "SELECT id, tenant_id" in sql and "status = 'uploaded'" in sql:
            return _RecoveryResult(self._queued_rows)
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_recovery_resets_stale_and_requeues_by_tenant(monkeypatch):
    session = _RecoverySession(
        stale_rows=[("doc-stale",)],
        queued_rows=[
            {"id": "doc-stale", "tenant_id": "tenant-a"},
            {"id": "doc-next", "tenant_id": "tenant-a"},
            {"id": "doc-other", "tenant_id": "tenant-b"},
        ],
    )
    started: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        knowledge,
        "_start_ingestion",
        lambda document_ids, tenant_id: started.append(
            (tenant_id, list(document_ids))
        ),
    )

    result = await knowledge.recover_interrupted_ingestion()

    assert result == {
        "stale_parsing": 1,
        "queued": 3,
        "tenants": 2,
    }
    assert started == [
        ("tenant-a", ["doc-stale", "doc-next"]),
        ("tenant-b", ["doc-other"]),
    ]
    assert session.committed is True
    assert any("WHERE status = 'parsing'" in sql for sql in session.executed_sql)


@pytest.mark.asyncio
async def test_recovery_deduplicates_document_ids(monkeypatch):
    session = _RecoverySession(
        stale_rows=[],
        queued_rows=[
            {"id": "doc-1", "tenant_id": "tenant-a"},
            {"id": "doc-1", "tenant_id": "tenant-a"},
        ],
    )
    started: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        knowledge,
        "_start_ingestion",
        lambda document_ids, tenant_id: started.append(
            (tenant_id, list(document_ids))
        ),
    )

    result = await knowledge.recover_interrupted_ingestion()

    assert result["queued"] == 1
    assert started == [("tenant-a", ["doc-1"])]


@pytest.mark.asyncio
async def test_recovery_is_noop_when_queue_empty(monkeypatch):
    session = _RecoverySession(stale_rows=[], queued_rows=[])
    started: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        knowledge,
        "_start_ingestion",
        lambda document_ids, tenant_id: started.append(
            (tenant_id, list(document_ids))
        ),
    )

    result = await knowledge.recover_interrupted_ingestion()

    assert result == {
        "stale_parsing": 0,
        "queued": 0,
        "tenants": 0,
    }
    assert started == []
