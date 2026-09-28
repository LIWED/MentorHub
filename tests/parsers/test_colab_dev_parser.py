from __future__ import annotations

import json
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core.parsers.colab_dev import (
    ColabDevParser,
    ColabDevParserError,
)
from backend.core.parsers.mineru import MinerUParser
from backend.core.parsers.registry import ParserRegistry


def _write_result_zip(path: Path, *, job_id: str) -> None:
    payload = {
        "ok": True,
        "job_id": job_id,
        "content_format": "markdown",
        "documents": [
            {
                "page_content": "# 课程\n\n远程解析正文",
                "metadata": {
                    "source_name": "lesson",
                    "parser": "mineru",
                    "content_format": "markdown",
                },
            }
        ],
        "metadata": {
            "tier": "flash",
            "image_count": 1,
            "image_enriched_count": 1,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "result.json",
            json.dumps(payload, ensure_ascii=False),
        )
        archive.writestr("markdown.md", "# 课程\n\n远程解析正文")


def test_colab_job_packages_html_and_relative_image(tmp_path: Path):
    root = tmp_path / "course"
    page = root / "lessons" / "1.1.html"
    image = root / "img" / "diagram.png"
    page.parent.mkdir(parents=True)
    image.parent.mkdir(parents=True)
    page.write_text(
        '<h1>课程</h1><img alt="架构图" src="../img/diagram.png">',
        encoding="utf-8",
    )
    image.write_bytes(b"fake-image")

    parser = ColabDevParser(
        queue_root=tmp_path / "drive",
        output_root=tmp_path / "out",
        timeout_seconds=5,
    )
    job_id = parser._job_id(page, "doc-1")
    job_zip = parser._build_job_zip(
        page,
        job_id=job_id,
        document_id="doc-1",
    )

    with zipfile.ZipFile(job_zip, "r") as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("job.json").decode("utf-8"))

    assert manifest["job_id"] == job_id
    assert manifest["source_relpath"] == "lessons/1.1.html"
    assert "source/lessons/1.1.html" in names
    assert "source/img/diagram.png" in names


def test_colab_parser_imports_completed_result(tmp_path: Path, monkeypatch):
    source = tmp_path / "lesson.html"
    source.write_text("<h1>课程</h1>", encoding="utf-8")
    queue = tmp_path / "drive"

    parser = ColabDevParser(
        queue_root=queue,
        output_root=tmp_path / "mineru",
        timeout_seconds=5,
        poll_seconds=0.01,
    )
    # parse() 会同步 worker bundle；测试中不需要真实 worker 文件复制。
    monkeypatch.setattr(parser, "_sync_worker_bundle", lambda: None)

    job_id = parser._job_id(source, "doc-1")
    _write_result_zip(queue / "done" / f"{job_id}.zip", job_id=job_id)

    result = parser.parse(source, document_id="doc-1")

    assert result.parser_name == "mineru"
    assert result.content_format == "markdown"
    assert result.documents[0].page_content.endswith("远程解析正文")
    assert result.documents[0].metadata["remote_parser"] == "colab_dev"
    assert result.metadata["job_id"] == job_id
    assert result.metadata["image_enriched_count"] == 1


def test_colab_parser_surfaces_remote_failure_without_local_fallback(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "lesson.html"
    source.write_text("<h1>课程</h1>", encoding="utf-8")
    queue = tmp_path / "drive"

    parser = ColabDevParser(
        queue_root=queue,
        output_root=tmp_path / "mineru",
        timeout_seconds=5,
        poll_seconds=0.01,
    )
    monkeypatch.setattr(parser, "_sync_worker_bundle", lambda: None)

    job_id = parser._job_id(source, "doc-1")
    failed = queue / "failed" / f"{job_id}.error.json"
    def publish_failure():
        failed.parent.mkdir(parents=True, exist_ok=True)
        failed.write_text(
            json.dumps({"error": "GPU worker failed"}, ensure_ascii=False),
            encoding="utf-8",
        )

    timer = threading.Timer(0.05, publish_failure)
    timer.start()

    try:
        with pytest.raises(ColabDevParserError, match="GPU worker failed"):
            parser.parse(source, document_id="doc-1")
    finally:
        timer.cancel()


def test_registry_default_mode_remains_local(tmp_path: Path, monkeypatch):
    import backend.core.parsers.registry as registry_module

    fake_settings = SimpleNamespace(parser_mode="local")
    monkeypatch.setattr(registry_module, "get_settings", lambda: fake_settings)

    registry = registry_module.ParserRegistry()
    assert isinstance(registry.mineru, MinerUParser)


def test_registry_can_switch_to_colab_dev(tmp_path: Path, monkeypatch):
    import backend.core.parsers.colab_dev as colab_module
    import backend.core.parsers.registry as registry_module

    fake_settings = SimpleNamespace(
        parser_mode="colab_dev",
        colab_parser_job_root=str(tmp_path / "drive"),
        colab_parser_poll_seconds=0.01,
        colab_parser_timeout_seconds=5,
        mineru_tier="basic",
        mineru_output_root=str(tmp_path / "mineru"),
    )
    monkeypatch.setattr(registry_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(colab_module, "get_settings", lambda: fake_settings)

    registry = registry_module.ParserRegistry()

    assert isinstance(registry.mineru, ColabDevParser)
