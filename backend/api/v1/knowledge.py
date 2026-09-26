from __future__ import annotations

import asyncio
import os
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.config import get_settings
from backend.core.knowledge_base import KnowledgeBaseClient
from backend.core.knowledge_management import (
    UploadedFileEntry,
    discover_ingestible_files,
    get_course_upload_root,
    normalize_relative_path,
    remove_empty_parent_dirs,
    resolve_upload_destination,
    sha256_file,
)
from backend.core.logger import get_logger
from backend.dependencies import AsyncSessionLocal, get_current_user

router = APIRouter()
logger = get_logger(__name__)

_background_tasks: set[asyncio.Task] = set()
_index_lock = threading.Lock()


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class CourseView(BaseModel):
    id: str
    name: str
    description: str = ""
    document_count: int = 0
    completed_count: int = 0
    chunk_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class DocumentView(BaseModel):
    id: str
    course_id: str
    filename: str
    relative_path: str
    file_type: str
    status: Literal["uploaded", "parsing", "completed", "failed"]
    parser: str | None = None
    content_format: str | None = None
    extracted_chars: int = 0
    chunk_count: int = 0
    image_count: int = 0
    image_enriched_count: int = 0
    image_failed_count: int = 0
    error_msg: str | None = None
    updated_at: str | None = None


class UploadBatchView(BaseModel):
    uploaded_files: int
    documents_queued: int
    skipped_unchanged: int
    asset_files: int
    sitemap_used: bool


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可以管理课程知识库",
        )
    return current_user


def _row_to_course(row) -> CourseView:
    data = dict(row)
    return CourseView(
        id=str(data["id"]),
        name=data["name"],
        description=data.get("description") or "",
        document_count=int(data.get("document_count") or 0),
        completed_count=int(data.get("completed_count") or 0),
        chunk_count=int(data.get("chunk_count") or 0),
        created_at=data.get("created_at").isoformat() if data.get("created_at") else None,
        updated_at=data.get("updated_at").isoformat() if data.get("updated_at") else None,
    )


def _row_to_document(row) -> DocumentView:
    data = dict(row)
    return DocumentView(
        id=str(data["id"]),
        course_id=str(data["course_id"]),
        filename=data["filename"],
        relative_path=data["relative_path"],
        file_type=data["file_type"],
        status=data["status"],
        parser=data.get("parser"),
        content_format=data.get("content_format"),
        extracted_chars=int(data.get("extracted_chars") or 0),
        chunk_count=int(data.get("chunk_count") or 0),
        image_count=int(data.get("image_count") or 0),
        image_enriched_count=int(data.get("image_enriched_count") or 0),
        image_failed_count=int(data.get("image_failed_count") or 0),
        error_msg=data.get("error_msg"),
        updated_at=data.get("updated_at").isoformat() if data.get("updated_at") else None,
    )


async def _get_course_row(course_id: str, tenant_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT c.id, c.name, c.description, c.created_at, c.updated_at,
                       COUNT(d.id)::int AS document_count,
                       COUNT(d.id) FILTER (WHERE d.status = 'completed')::int AS completed_count,
                       COALESCE(SUM(d.chunk_count), 0)::int AS chunk_count
                FROM knowledge_courses c
                LEFT JOIN knowledge_documents d ON d.course_id = c.id
                WHERE c.id = :course_id AND c.tenant_id = :tenant_id
                GROUP BY c.id
                """
            ),
            {"course_id": course_id, "tenant_id": tenant_id},
        )
        return result.mappings().first()


async def _write_upload_to_temp(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(
        destination.name + f".{uuid.uuid4().hex}.upload"
    )
    size = 0
    try:
        with temp_path.open("wb") as handle:
            while True:
                block = await upload.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件过大：{upload.filename}，单文件最大 {max_bytes // 1024 // 1024}MB",
                    )
                handle.write(block)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"上传文件为空：{upload.filename}")
    return temp_path


def _run_pipeline_sync(
    *,
    file_path: str,
    course_id: str,
    document_id: str,
    tenant_id: str,
) -> dict:
    # BM25 当前按全库重建；串行化写入，避免两个后台 ingestion 同时覆盖稀疏权重。
    with _index_lock:
        # 延迟导入，避免 API 启动阶段加载 ingestion 脚本及其本地模型依赖。
        from scripts.build_knowledge_base import build_pipeline

        return asyncio.run(
            build_pipeline(
                file_path=file_path,
                course_id=course_id,
                document_id=document_id,
                tenant_id=tenant_id,
                use_context=False,
            )
        )


async def _mark_document_failed(document_id: str, tenant_id: str, exc: Exception) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'failed', error_msg = :error_msg, updated_at = NOW()
                WHERE id = :document_id AND tenant_id = :tenant_id
                """
            ),
            {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "error_msg": str(exc)[:2000],
            },
        )
        await session.commit()


async def _ingest_document(document_id: str, tenant_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id, course_id, storage_path
                FROM knowledge_documents
                WHERE id = :document_id AND tenant_id = :tenant_id
                """
            ),
            {"document_id": document_id, "tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            return
        await session.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'parsing', error_msg = NULL, updated_at = NOW()
                WHERE id = :document_id
                """
            ),
            {"document_id": document_id},
        )
        await session.commit()

    try:
        stats = await asyncio.to_thread(
            _run_pipeline_sync,
            file_path=row["storage_path"],
            course_id=str(row["course_id"]),
            document_id=str(row["id"]),
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error(
            "knowledge.document_ingest_failed",
            document_id=document_id,
            error=str(exc),
            exc_info=exc,
        )
        await _mark_document_failed(document_id, tenant_id, exc)
        return

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'completed',
                    parser = :parser,
                    content_format = :content_format,
                    extracted_chars = :extracted_chars,
                    chunk_count = :chunk_count,
                    image_count = :image_count,
                    image_enriched_count = :image_enriched_count,
                    image_failed_count = :image_failed_count,
                    error_msg = NULL,
                    updated_at = NOW()
                WHERE id = :document_id AND tenant_id = :tenant_id
                """
            ),
            {
                "document_id": document_id,
                "tenant_id": tenant_id,
                **stats,
            },
        )
        await session.commit()
    logger.info(
        "knowledge.document_ingest_done",
        document_id=document_id,
        chunks=stats.get("chunk_count", 0),
    )


async def _ingest_batch(document_ids: list[str], tenant_id: str) -> None:
    # 同一批次顺序处理：既减少本地模型争用，也与当前全库 BM25 重建策略一致。
    for document_id in document_ids:
        await _ingest_document(document_id, tenant_id)


def _start_ingestion(document_ids: list[str], tenant_id: str) -> None:
    if not document_ids:
        return
    task = asyncio.create_task(_ingest_batch(document_ids, tenant_id))
    _background_tasks.add(task)

    def _done(completed: asyncio.Task) -> None:
        _background_tasks.discard(completed)
        if not completed.cancelled() and completed.exception():
            logger.error(
                "knowledge.batch_ingest_failed",
                error=str(completed.exception()),
                exc_info=completed.exception(),
            )

    task.add_done_callback(_done)


@router.post("/courses", response_model=CourseView, status_code=201)
async def create_course(
    payload: CourseCreate,
    current_user: dict = Depends(require_admin),
) -> CourseView:
    tenant_id = current_user["tenant_id"]
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="课程名称不能为空")
    async with AsyncSessionLocal() as session:
        exists = await session.execute(
            text(
                "SELECT id FROM knowledge_courses "
                "WHERE tenant_id = :tenant_id AND name = :name LIMIT 1"
            ),
            {"tenant_id": tenant_id, "name": name},
        )
        if exists.first():
            raise HTTPException(status_code=409, detail="当前租户下已存在同名课程")

        result = await session.execute(
            text(
                """
                INSERT INTO knowledge_courses (tenant_id, name, description, created_by)
                VALUES (:tenant_id, :name, :description, :created_by)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "name": name,
                "description": payload.description.strip(),
                "created_by": current_user["user_id"],
            },
        )
        course_id = str(result.scalar_one())
        await session.commit()

    row = await _get_course_row(course_id, tenant_id)
    return _row_to_course(row)


@router.get("/courses", response_model=list[CourseView])
async def list_courses(
    current_user: dict = Depends(require_admin),
) -> list[CourseView]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT c.id, c.name, c.description, c.created_at, c.updated_at,
                       COUNT(d.id)::int AS document_count,
                       COUNT(d.id) FILTER (WHERE d.status = 'completed')::int AS completed_count,
                       COALESCE(SUM(d.chunk_count), 0)::int AS chunk_count
                FROM knowledge_courses c
                LEFT JOIN knowledge_documents d ON d.course_id = c.id
                WHERE c.tenant_id = :tenant_id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                """
            ),
            {"tenant_id": current_user["tenant_id"]},
        )
        return [_row_to_course(row) for row in result.mappings().all()]


@router.get("/courses/{course_id}", response_model=CourseView)
async def get_course(
    course_id: str,
    current_user: dict = Depends(require_admin),
) -> CourseView:
    row = await _get_course_row(course_id, current_user["tenant_id"])
    if not row:
        raise HTTPException(status_code=404, detail="课程不存在")
    return _row_to_course(row)


@router.get("/courses/{course_id}/documents", response_model=list[DocumentView])
async def list_documents(
    course_id: str,
    current_user: dict = Depends(require_admin),
) -> list[DocumentView]:
    tenant_id = current_user["tenant_id"]
    if not await _get_course_row(course_id, tenant_id):
        raise HTTPException(status_code=404, detail="课程不存在")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id, course_id, filename, relative_path, file_type, status,
                       parser, content_format, extracted_chars, chunk_count,
                       image_count, image_enriched_count, image_failed_count,
                       error_msg, updated_at
                FROM knowledge_documents
                WHERE course_id = :course_id AND tenant_id = :tenant_id
                ORDER BY relative_path ASC
                """
            ),
            {"course_id": course_id, "tenant_id": tenant_id},
        )
        return [_row_to_document(row) for row in result.mappings().all()]


@router.post(
    "/courses/{course_id}/documents",
    response_model=UploadBatchView,
    status_code=202,
)
async def upload_documents(
    course_id: str,
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(default=None),
    upload_mode: Literal["files", "folder"] = Form(default="files"),
    current_user: dict = Depends(require_admin),
) -> UploadBatchView:
    tenant_id = current_user["tenant_id"]
    if not await _get_course_row(course_id, tenant_id):
        raise HTTPException(status_code=404, detail="课程不存在")
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")

    paths = relative_paths or []
    if paths and len(paths) != len(files):
        raise HTTPException(status_code=400, detail="relative_paths 与 files 数量不一致")

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for index, upload in enumerate(files):
        raw = paths[index] if paths else upload.filename
        try:
            relative_path = normalize_relative_path(raw, upload.filename or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if relative_path in seen:
            raise HTTPException(status_code=400, detail=f"上传包存在重复路径：{relative_path}")
        seen.add(relative_path)
        normalized_paths.append(relative_path)

    # 正在解析的源文件不能被覆盖，否则后台 Parser 可能读到一半变化的文件。
    async with AsyncSessionLocal() as session:
        active = await session.execute(
            text(
                """
                SELECT relative_path
                FROM knowledge_documents
                WHERE course_id = :course_id
                  AND tenant_id = :tenant_id
                  AND status IN ('uploaded', 'parsing')
                """
            ),
            {"course_id": course_id, "tenant_id": tenant_id},
        )
        active_paths = {row[0] for row in active.fetchall()}
    conflicts = sorted(set(normalized_paths) & active_paths)
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"文档正在处理中，请完成后再覆盖：{conflicts[0]}",
        )

    settings = get_settings()
    max_bytes = settings.knowledge_upload_max_file_mb * 1024 * 1024
    staged: list[tuple[Path, Path, str]] = []

    try:
        for upload, relative_path in zip(files, normalized_paths):
            destination = resolve_upload_destination(
                tenant_id, course_id, relative_path
            )
            temp_path = await _write_upload_to_temp(
                upload, destination, max_bytes=max_bytes
            )
            staged.append((temp_path, destination, relative_path))
    except Exception:
        for temp_path, _, _ in staged:
            temp_path.unlink(missing_ok=True)
        raise

    # 所有文件均完成读取后再原子替换，避免上传到一半就留下半套网页资源。
    for temp_path, destination, _ in staged:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, destination)

    entries = [
        UploadedFileEntry(relative_path=relative_path, absolute_path=destination)
        for _, destination, relative_path in staged
    ]
    discovery = discover_ingestible_files(
        entries,
        folder_mode=upload_mode == "folder",
    )
    if not discovery.documents:
        raise HTTPException(
            status_code=400,
            detail="上传内容中没有发现可入库的文档文件",
        )

    queued_ids: list[str] = []
    skipped = 0
    async with AsyncSessionLocal() as session:
        for entry in discovery.documents:
            file_hash = sha256_file(entry.absolute_path)
            existing = await session.execute(
                text(
                    """
                    SELECT id, file_hash, status
                    FROM knowledge_documents
                    WHERE course_id = :course_id
                      AND tenant_id = :tenant_id
                      AND relative_path = :relative_path
                    LIMIT 1
                    """
                ),
                {
                    "course_id": course_id,
                    "tenant_id": tenant_id,
                    "relative_path": entry.relative_path,
                },
            )
            existing_row = existing.mappings().first()

            # 文件夹整体上传时，即使 HTML 本身未变化，img/assets 也可能变化，
            # 所以仍重新解析；普通文件上传则跳过完全未变化的完成文档。
            if (
                upload_mode == "files"
                and existing_row
                and existing_row["file_hash"] == file_hash
                and existing_row["status"] == "completed"
            ):
                skipped += 1
                continue

            document_id = (
                str(existing_row["id"]) if existing_row else str(uuid.uuid4())
            )
            await session.execute(
                text(
                    """
                    INSERT INTO knowledge_documents (
                        id, tenant_id, course_id, filename, relative_path,
                        file_type, storage_path, file_hash, status, created_by
                    )
                    VALUES (
                        :id, :tenant_id, :course_id, :filename, :relative_path,
                        :file_type, :storage_path, :file_hash, 'uploaded', :created_by
                    )
                    ON CONFLICT (course_id, relative_path)
                    DO UPDATE SET
                        filename = EXCLUDED.filename,
                        file_type = EXCLUDED.file_type,
                        storage_path = EXCLUDED.storage_path,
                        file_hash = EXCLUDED.file_hash,
                        status = 'uploaded',
                        parser = NULL,
                        content_format = NULL,
                        extracted_chars = 0,
                        chunk_count = 0,
                        image_count = 0,
                        image_enriched_count = 0,
                        image_failed_count = 0,
                        error_msg = NULL,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": document_id,
                    "tenant_id": tenant_id,
                    "course_id": course_id,
                    "filename": entry.absolute_path.name,
                    "relative_path": entry.relative_path,
                    "file_type": entry.absolute_path.suffix.lower().lstrip(".") or "unknown",
                    "storage_path": str(entry.absolute_path),
                    "file_hash": file_hash,
                    "created_by": current_user["user_id"],
                },
            )
            queued_ids.append(document_id)
        await session.commit()

    _start_ingestion(queued_ids, tenant_id)
    return UploadBatchView(
        uploaded_files=len(entries),
        documents_queued=len(queued_ids),
        skipped_unchanged=skipped,
        asset_files=discovery.asset_count,
        sitemap_used=discovery.sitemap_used,
    )


@router.post("/documents/{document_id}/reparse", status_code=202)
async def reparse_document(
    document_id: str,
    current_user: dict = Depends(require_admin),
):
    tenant_id = current_user["tenant_id"]
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'uploaded', error_msg = NULL, updated_at = NOW()
                WHERE id = :document_id AND tenant_id = :tenant_id
                  AND status IN ('completed', 'failed')
                RETURNING id
                """
            ),
            {"document_id": document_id, "tenant_id": tenant_id},
        )
        row = result.first()
        if not row:
            exists = await session.execute(
                text(
                    "SELECT status FROM knowledge_documents "
                    "WHERE id = :document_id AND tenant_id = :tenant_id"
                ),
                {"document_id": document_id, "tenant_id": tenant_id},
            )
            if exists.first():
                raise HTTPException(status_code=409, detail="文档正在处理中")
            raise HTTPException(status_code=404, detail="文档不存在")
        await session.commit()

    _start_ingestion([document_id], tenant_id)
    return {"document_id": document_id, "status": "uploaded"}


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    current_user: dict = Depends(require_admin),
) -> None:
    tenant_id = current_user["tenant_id"]
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id, course_id, storage_path, status
                FROM knowledge_documents
                WHERE id = :document_id AND tenant_id = :tenant_id
                """
            ),
            {"document_id": document_id, "tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        if row["status"] in {"uploaded", "parsing"}:
            raise HTTPException(status_code=409, detail="文档正在处理中，暂不能删除")

    def _delete_vectors() -> None:
        with _index_lock:
            KnowledgeBaseClient().delete_document_and_rebuild(document_id)

    await asyncio.to_thread(_delete_vectors)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "DELETE FROM knowledge_documents "
                "WHERE id = :document_id AND tenant_id = :tenant_id"
            ),
            {"document_id": document_id, "tenant_id": tenant_id},
        )
        await session.commit()

    storage_path = Path(row["storage_path"])
    storage_path.unlink(missing_ok=True)
    remove_empty_parent_dirs(
        storage_path,
        stop_at=get_course_upload_root(tenant_id, str(row["course_id"])),
    )
