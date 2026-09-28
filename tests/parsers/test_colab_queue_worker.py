from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.colab_queue_worker import process_one, recover_processing


def test_colab_queue_worker_claims_job_and_publishes_result(tmp_path: Path):
    queue = tmp_path / "queue"
    for name in ("pending", "processing", "done", "failed", "worker"):
        (queue / name).mkdir(parents=True)

    fake_parser = queue / "worker" / "colab_parse_job.py"
    fake_parser.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--job-root", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
manifest = json.loads((Path(args.job_root) / "job.json").read_text(encoding="utf-8"))
(output / "result.json").write_text(
    json.dumps(
        {
            "ok": True,
            "job_id": manifest["job_id"],
            "documents": [{"page_content": "ok", "metadata": {}}],
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
""".strip(),
        encoding="utf-8",
    )

    job = queue / "pending" / "job-1.zip"
    with zipfile.ZipFile(job, "w") as archive:
        archive.writestr(
            "job.json",
            json.dumps(
                {
                    "job_id": "job-1",
                    "source_name": "lesson.html",
                    "source_relpath": "lesson.html",
                }
            ),
        )
        archive.writestr("source/lesson.html", "<h1>lesson</h1>")

    process_one(queue, job, tmp_path / "work")

    result_zip = queue / "done" / "job-1.zip"
    assert result_zip.exists()
    assert not (queue / "processing" / "job-1.zip").exists()
    assert not (queue / "failed" / "job-1.error.json").exists()

    with zipfile.ZipFile(result_zip, "r") as archive:
        payload = json.loads(archive.read("result.json").decode("utf-8"))
    assert payload["ok"] is True
    assert payload["job_id"] == "job-1"


def test_colab_queue_worker_recovers_interrupted_processing(tmp_path: Path):
    queue = tmp_path / "queue"
    for name in ("pending", "processing", "done", "failed", "worker"):
        (queue / name).mkdir(parents=True)

    interrupted = queue / "processing" / "job-2.zip"
    interrupted.write_bytes(b"job")

    recovered = recover_processing(queue)

    assert recovered == 1
    assert not interrupted.exists()
    assert (queue / "pending" / "job-2.zip").read_bytes() == b"job"
