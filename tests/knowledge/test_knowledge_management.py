from pathlib import Path

import pytest

from backend.core.knowledge_management import (
    UploadedFileEntry,
    discover_ingestible_files,
    normalize_relative_path,
)


def _entry(root: Path, relative: str, content: str = "x") -> UploadedFileEntry:
    path = root / Path(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return UploadedFileEntry(relative_path=relative, absolute_path=path)


def test_normalize_relative_path_preserves_folder_and_rejects_traversal():
    assert (
        normalize_relative_path(
            r"课程\② 核心技术基础\2.4 ReAct.html",
            "2.4 ReAct.html",
        )
        == "课程/② 核心技术基础/2.4 ReAct.html"
    )

    with pytest.raises(ValueError):
        normalize_relative_path("../secret.txt", "secret.txt")

    with pytest.raises(ValueError):
        normalize_relative_path(r"C:\secret.txt", "secret.txt")


def test_folder_upload_uses_sitemap_and_keeps_assets_out_of_documents(tmp_path):
    entries = [
        _entry(
            tmp_path,
            "site/sitemap.xml",
            """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/②%20核心技术基础/2.4%20ReAct.html</loc></url>
            </urlset>""",
        ),
        _entry(tmp_path, "site/② 核心技术基础/2.4 ReAct.html", "<h1>ReAct</h1>"),
        _entry(tmp_path, "site/② 核心技术基础/2.5 Agent.html", "<h1>Agent</h1>"),
        _entry(tmp_path, "site/index.html", "<a>导航</a>"),
        _entry(tmp_path, "site/404.html", "not found"),
        _entry(tmp_path, "site/img/AI.jpg", "fake-image"),
        _entry(tmp_path, "site/补充.md", "# 补充"),
    ]

    result = discover_ingestible_files(entries, folder_mode=True)

    assert result.sitemap_used is True
    paths = [item.relative_path for item in result.documents]
    assert "site/② 核心技术基础/2.4 ReAct.html" in paths
    assert "site/补充.md" in paths
    assert "site/② 核心技术基础/2.5 Agent.html" not in paths
    assert "site/index.html" not in paths
    assert "site/img/AI.jpg" not in paths
    assert result.asset_count == len(entries) - len(result.documents)


def test_folder_upload_without_sitemap_falls_back_to_content_html(tmp_path):
    entries = [
        _entry(tmp_path, "course/index.html", "nav"),
        _entry(tmp_path, "course/404.html", "404"),
        _entry(tmp_path, "course/search/search.html", "search"),
        _entry(tmp_path, "course/01/a.html", "A"),
        _entry(tmp_path, "course/02/b.html", "B"),
    ]

    result = discover_ingestible_files(entries, folder_mode=True)

    assert result.sitemap_used is False
    assert [item.relative_path for item in result.documents] == [
        "course/01/a.html",
        "course/02/b.html",
    ]


def test_image_is_document_for_file_upload_but_asset_for_folder_upload(tmp_path):
    image = _entry(tmp_path, "diagram.png", "fake-image")

    file_result = discover_ingestible_files([image], folder_mode=False)
    folder_result = discover_ingestible_files([image], folder_mode=True)

    assert [item.relative_path for item in file_result.documents] == ["diagram.png"]
    assert folder_result.documents == []
    assert folder_result.asset_count == 1


def _chunk(document_id: str, content: str):
    from backend.core.knowledge_base import DocumentChunk

    return DocumentChunk(
        id=f"{document_id}-{content}",
        content=content,
        embedding=[0.1],
        sparse_embedding={},
        course_id="course",
        document_id=document_id,
        source_name="source",
        chunk_type="text",
        chunk_index=0,
        version="1.0",
    )


def test_document_update_deletes_old_chunks_before_upsert(monkeypatch):
    from backend.core.knowledge_base import KnowledgeBaseClient

    client = object.__new__(KnowledgeBaseClient)
    existing = [_chunk("other", "existing")]
    new_chunks = [_chunk("target", "new")]
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        client,
        "list_chunks",
        lambda exclude_document_id=None: existing,
    )
    monkeypatch.setattr(
        client,
        "delete_document_chunks",
        lambda document_id: events.append(("delete", document_id)),
    )
    monkeypatch.setattr(
        client,
        "upsert_chunks",
        lambda chunks: events.append(
            ("upsert", [chunk.document_id for chunk in chunks])
        ) or len(chunks),
    )

    written = client.upsert_with_bm25_rebuild(new_chunks)

    assert written == 1
    assert events[0] == ("delete", "target")
    assert events[1] == ("upsert", ["other", "target"])


def test_document_delete_rebuilds_remaining_bm25(monkeypatch):
    from backend.core.knowledge_base import KnowledgeBaseClient

    client = object.__new__(KnowledgeBaseClient)
    remaining = [_chunk("other", "alpha beta")]
    events: list[str] = []

    monkeypatch.setattr(
        client,
        "list_chunks",
        lambda exclude_document_id=None: remaining,
    )
    monkeypatch.setattr(
        client,
        "delete_document_chunks",
        lambda document_id: events.append(f"delete:{document_id}"),
    )
    monkeypatch.setattr(
        client,
        "upsert_chunks",
        lambda chunks: events.append(f"upsert:{len(chunks)}") or len(chunks),
    )

    client.delete_document_and_rebuild("target")

    assert events == ["delete:target", "upsert:1"]
    assert remaining[0].sparse_embedding
