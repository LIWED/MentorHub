"""
Google Colab queue worker for MentorHub development parsing.

Queue structure:
  pending/*.zip -> processing/*.zip -> done/*.zip
                                  -> failed/*.error.json

The job itself is copied to /content before parsing so MinerU never performs
heavy small-file I/O directly on the mounted Google Drive.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    target = target.resolve()
    for member in archive.infolist():
        output = (target / member.filename).resolve()
        if os.path.commonpath([str(target), str(output)]) != str(target):
            raise RuntimeError(f"unsafe zip path: {member.filename}")
    archive.extractall(target)


def _zip_directory(source: Path, output_zip: Path) -> None:
    temp = output_zip.with_suffix(".zip.tmp")
    temp.unlink(missing_ok=True)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    os.replace(temp, output_zip)


def process_one(queue_root: Path, job_zip: Path, work_root: Path) -> None:
    processing = queue_root / "processing" / job_zip.name
    done = queue_root / "done" / job_zip.name
    failed = queue_root / "failed" / f"{job_zip.stem}.error.json"
    status_dir = queue_root / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    status_file = status_dir / f"{job_zip.stem}.json"

    def write_status(phase: str, **extra) -> None:
        payload = {
            "job_id": job_zip.stem,
            "phase": phase,
            "updated_at": int(time.time()),
            **extra,
        }
        temp = status_file.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp, status_file)

    if done.exists():
        job_zip.unlink(missing_ok=True)
        return

    try:
        os.replace(job_zip, processing)
    except FileNotFoundError:
        return
    write_status("claimed")

    local_job = work_root / job_zip.stem
    if local_job.exists():
        shutil.rmtree(local_job)
    local_job.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(processing, "r") as archive:
            _safe_extract(archive, local_job)

        manifest = json.loads((local_job / "job.json").read_text(encoding="utf-8"))
        job_id = str(manifest.get("job_id") or job_zip.stem)
        print(
            f"[worker] start {job_id}: {manifest.get('source_name')}",
            flush=True,
        )
        write_status(
            "parsing",
            source_name=manifest.get("source_name"),
            tier=manifest.get("tier"),
        )

        output_dir = local_job / "result"
        parse_script = queue_root / "worker" / "colab_parse_job.py"
        completed = subprocess.run(
            [
                sys.executable,
                "-u",
                str(parse_script),
                "--job-root",
                str(local_job),
                "--output",
                str(output_dir),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error")[-6000:]
            raise RuntimeError(detail)

        done.parent.mkdir(parents=True, exist_ok=True)
        local_result_zip = local_job / "result.zip"
        _zip_directory(output_dir, local_result_zip)

        drive_temp = done.with_suffix(".zip.tmp")
        shutil.copy2(local_result_zip, drive_temp)
        os.replace(drive_temp, done)

        failed.unlink(missing_ok=True)
        processing.unlink(missing_ok=True)
        write_status("done")
        print(f"[worker] done  {job_id}", flush=True)
    except Exception as exc:
        failed.parent.mkdir(parents=True, exist_ok=True)
        failed.write_text(
            json.dumps(
                {
                    "ok": False,
                    "job_id": job_zip.stem,
                    "error": str(exc),
                    "failed_at": int(time.time()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        processing.unlink(missing_ok=True)
        write_status("failed", error=str(exc))
        print(
            f"[worker] failed {job_zip.stem}: {exc}",
            file=sys.stderr,
            flush=True,
        )
    finally:
        shutil.rmtree(local_job, ignore_errors=True)


def recover_processing(queue_root: Path) -> int:
    """
    Colab Runtime 断开时 processing 里的 ZIP 会遗留。
    新 Worker 启动后把未完成任务重新放回 pending。
    """
    recovered = 0
    processing_dir = queue_root / "processing"
    for job in sorted(processing_dir.glob("*.zip")):
        done = queue_root / "done" / job.name
        failed = queue_root / "failed" / f"{job.stem}.error.json"
        if done.exists() or failed.exists():
            job.unlink(missing_ok=True)
            continue
        pending = queue_root / "pending" / job.name
        if not pending.exists():
            os.replace(job, pending)
            recovered += 1
    return recovered


def run(queue_root: Path, *, poll_seconds: float, once: bool) -> None:
    for name in ("pending", "processing", "done", "failed", "worker", "status"):
        (queue_root / name).mkdir(parents=True, exist_ok=True)

    work_root = Path("/content/mentorhub_colab_jobs")
    if not Path("/content").exists():
        work_root = Path(tempfile.gettempdir()) / "mentorhub_colab_jobs"
    work_root.mkdir(parents=True, exist_ok=True)

    recovered = recover_processing(queue_root)
    print(f"[worker] queue: {queue_root}", flush=True)
    print(f"[worker] local work: {work_root}", flush=True)
    if recovered:
        print(
            f"[worker] recovered {recovered} interrupted job(s)",
            flush=True,
        )
    print("[worker] ready", flush=True)

    while True:
        jobs = sorted((queue_root / "pending").glob("*.zip"))
        for job in jobs:
            process_one(queue_root, job, work_root)
        if once:
            return
        time.sleep(max(1.0, poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-root", required=True)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run(
        Path(args.queue_root).expanduser().resolve(),
        poll_seconds=args.poll_seconds,
        once=args.once,
    )


if __name__ == "__main__":
    main()
