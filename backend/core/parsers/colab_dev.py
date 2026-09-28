from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from langchain_core.documents import Document

from backend.config import get_settings
from backend.core.logger import get_logger
from backend.core.parsers.base import DocumentParser, ParsedDocument
from backend.core.parsers.markdown_images import MarkdownImageResolver
from backend.core.parsers.mineru import MINERU_EXTENSIONS

logger = get_logger(__name__)

PROTOCOL_VERSION = 1
WORKER_REVISION = "2026-09-27-a"


class ColabDevParserError(RuntimeError):
    """开发期 Colab 解析器错误；不会自动退回本地 MinerU。"""


class ColabDevParser(DocumentParser):
    """
    仅开发环境使用的 Google Drive / Colab 解析客户端。

    本地负责打包与等待，Colab 负责 MinerU + 图片解析；
    最终仍返回 ParsedDocument，后续 Chunk/Embedding/Milvus 无需感知。
    """

    supported_extensions = MINERU_EXTENSIONS

    def __init__(
        self,
        *,
        queue_root: str | Path | None = None,
        poll_seconds: float | None = None,
        timeout_seconds: int | None = None,
        tier: str | None = None,
        output_root: str | Path | None = None,
    ):
        settings = get_settings()
        configured_root = queue_root or settings.colab_parser_job_root
        self.queue_root = (
            Path(configured_root).expanduser().resolve()
            if configured_root
            else None
        )
        self.poll_seconds = float(
            poll_seconds
            if poll_seconds is not None
            else settings.colab_parser_poll_seconds
        )
        self.timeout_seconds = int(
            timeout_seconds
            if timeout_seconds is not None
            else settings.colab_parser_timeout_seconds
        )
        self.tier = (tier or settings.mineru_tier or "basic").lower()
        self.output_root = Path(
            output_root or settings.mineru_output_root
        ).resolve()
        self.project_root = Path(__file__).resolve().parents[3]

    def _require_queue_root(self) -> Path:
        if self.queue_root is None:
            raise ColabDevParserError(
                "PARSER_MODE=colab_dev，但 COLAB_PARSER_JOB_ROOT 未配置。"
            )
        for name in ("pending", "processing", "done", "failed", "worker"):
            (self.queue_root / name).mkdir(parents=True, exist_ok=True)
        return self.queue_root

    def _sync_worker_bundle(self) -> None:
        root = self._require_queue_root()
        worker_dir = root / "worker"
        for name in ("colab_queue_worker.py", "colab_parse_job.py"):
            source = self.project_root / "scripts" / name
            if not source.exists():
                raise ColabDevParserError(f"Colab worker 文件不存在：{source}")
            target = worker_dir / name
            if not target.exists() or source.read_bytes() != target.read_bytes():
                shutil.copy2(source, target)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _effective_tier(self, path: Path) -> str:
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            return self.tier
        return "flash"

    def _job_id(self, path: Path, document_id: str | None) -> str:
        payload = "|".join(
            [
                str(PROTOCOL_VERSION),
                WORKER_REVISION,
                document_id or path.stem,
                self._sha256_file(path),
                self._effective_tier(path),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _collect_local_assets(path: Path) -> list[Path]:
        if path.suffix.lower() not in {".html", ".htm", ".md", ".markdown"}:
            return []

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        assets: list[Path] = []
        for ref in MarkdownImageResolver._find_image_references(text):
            if not ref.target or MarkdownImageResolver._is_remote(ref.target):
                continue
            try:
                asset = MarkdownImageResolver._resolve_local_image(
                    path,
                    ref.target,
                )
            except (OSError, ValueError):
                continue
            if asset not in assets:
                assets.append(asset)
        return assets

    @staticmethod
    def _archive_root(files: list[Path]) -> Path:
        parents = [str(path.resolve().parent) for path in files]
        return Path(os.path.commonpath(parents)).resolve()

    def _build_job_zip(
        self,
        path: Path,
        *,
        job_id: str,
        document_id: str | None,
    ) -> Path:
        root = self._require_queue_root()
        pending_path = root / "pending" / f"{job_id}.zip"
        if pending_path.exists():
            return pending_path

        source_files = [path, *self._collect_local_assets(path)]
        archive_root = self._archive_root(source_files)
        source_relpath = path.relative_to(archive_root).as_posix()
        manifest = {
            "protocol_version": PROTOCOL_VERSION,
            "worker_revision": WORKER_REVISION,
            "job_id": job_id,
            "document_id": document_id,
            "source_relpath": source_relpath,
            "source_name": path.name,
            "tier": self._effective_tier(path),
            "created_at": int(time.time()),
        }

        temp_path = pending_path.with_suffix(".zip.tmp")
        temp_path.unlink(missing_ok=True)
        with zipfile.ZipFile(
            temp_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "job.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            for file_path in source_files:
                relative = file_path.relative_to(archive_root).as_posix()
                archive.write(file_path, f"source/{relative}")

        os.replace(temp_path, pending_path)
        logger.info(
            "colab_parser.job_submitted",
            job_id=job_id,
            source=str(path),
            assets=max(0, len(source_files) - 1),
            queue=str(root),
        )
        return pending_path

    @staticmethod
    def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
        target = target.resolve()
        for member in archive.infolist():
            output = (target / member.filename).resolve()
            if os.path.commonpath([str(target), str(output)]) != str(target):
                raise ColabDevParserError(
                    f"远程结果包含非法路径：{member.filename}"
                )
        archive.extractall(target)

    def _load_result(
        self,
        result_zip: Path,
        source_path: Path,
        document_id: str | None,
    ) -> ParsedDocument:
        output_dir = self.output_root / (document_id or source_path.stem)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(result_zip, "r") as archive:
            self._safe_extract(archive, output_dir)

        result_path = output_dir / "result.json"
        if not result_path.exists():
            raise ColabDevParserError(
                f"Colab 结果缺少 result.json：{result_zip}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            raise ColabDevParserError(
                str(payload.get("error") or "Colab 解析失败")
            )

        documents: list[Document] = []
        for item in payload.get("documents") or []:
            metadata = dict(item.get("metadata") or {})
            metadata.update(
                {
                    "source": str(source_path),
                    "mineru_output_dir": str(output_dir),
                    "remote_parser": "colab_dev",
                }
            )
            documents.append(
                Document(
                    page_content=str(item.get("page_content") or ""),
                    metadata=metadata,
                )
            )
        if not documents:
            raise ColabDevParserError("Colab 返回结果没有可入库文档")

        metadata = dict(payload.get("metadata") or {})
        metadata.update(
            {
                "document_id": document_id,
                "remote_parser": "colab_dev",
                "job_id": payload.get("job_id"),
            }
        )
        return ParsedDocument(
            source_path=source_path,
            documents=documents,
            parser_name="mineru",
            content_format=str(payload.get("content_format") or "markdown"),
            output_dir=output_dir,
            asset_dir=(output_dir / "images")
            if (output_dir / "images").exists()
            else None,
            metadata=metadata,
        )

    def parse(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
    ) -> ParsedDocument:
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")
        if not self.supports(path):
            raise ValueError(f"Colab MinerU 不支持此扩展名：{path.suffix}")

        root = self._require_queue_root()
        self._sync_worker_bundle()
        job_id = self._job_id(path, document_id)
        done_path = root / "done" / f"{job_id}.zip"
        failed_path = root / "failed" / f"{job_id}.error.json"
        processing_path = root / "processing" / f"{job_id}.zip"

        # 上一次远程失败时，下一次显式“重新解析”允许自动重试；
        # 失败记录保留为 history 便于排查。
        if failed_path.exists():
            archived_failure = failed_path.with_name(
                f"{job_id}.error.{int(time.time())}.json"
            )
            os.replace(failed_path, archived_failure)

        if (
            not done_path.exists()
            and not processing_path.exists()
            and not failed_path.exists()
        ):
            self._build_job_zip(
                path,
                job_id=job_id,
                document_id=document_id,
            )

        started = time.monotonic()
        last_log = 0.0
        while True:
            if done_path.exists():
                logger.info(
                    "colab_parser.job_done",
                    job_id=job_id,
                    elapsed_seconds=round(time.monotonic() - started, 1),
                )
                return self._load_result(
                    done_path,
                    path,
                    document_id,
                )

            if failed_path.exists():
                try:
                    failure = json.loads(
                        failed_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    failure = {}
                raise ColabDevParserError(
                    str(
                        failure.get("error")
                        or f"Colab Worker 解析失败：{job_id}"
                    )
                )

            elapsed = time.monotonic() - started
            if elapsed >= self.timeout_seconds:
                raise ColabDevParserError(
                    f"等待 Colab Worker 超时（>{self.timeout_seconds}s）："
                    f"{path.name}。不会自动切回本地 MinerU。"
                )

            if elapsed - last_log >= 30:
                logger.info(
                    "colab_parser.waiting",
                    job_id=job_id,
                    elapsed_seconds=round(elapsed, 1),
                )
                last_log = elapsed
            time.sleep(max(0.2, self.poll_seconds))
