"""Run the resume Agent once and print its stage timings to the console."""

import argparse
import asyncio
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.resume.nodes import (  # noqa: E402
    diagnose_issues_node,
    extract_structured_node,
    extract_text_node,
    generate_summary_node,
    run_six_dimensions_node,
)
from backend.agents.resume.timing import (  # noqa: E402
    REQUIRED_TIMING_KEYS,
    collect_timings,
    format_timing_report,
    require_timings,
    timing_span,
)


DEFAULT_PDF = PROJECT_ROOT / "samples" / "sample1.pdf"
RESUME_NODES_LOGGER_NAME = "backend.agents.resume.nodes"


@contextmanager
def suppress_resume_node_logs():
    """Keep benchmark-only node logging from exposing resume content."""
    logger = logging.getLogger(RESUME_NODES_LOGGER_NAME)
    previous_disabled = logger.disabled
    logger.disabled = True
    try:
        yield
    finally:
        logger.disabled = previous_disabled


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行简历 Agent 计时基准。")
    parser.add_argument("--file", default=DEFAULT_PDF, help="要评审的 PDF 文件。")
    args = parser.parse_args()
    source = Path(args.file).resolve()
    if not source.exists() or not source.is_file():
        parser.error("指定文件不存在或不是普通文件。")
    if source.suffix.lower() != ".pdf":
        parser.error("指定文件必须是 PDF。")
    args.file = source
    return args


def build_initial_state(temp_path: str) -> dict:
    return {
        "messages": [],
        "student_id": str(uuid4()),
        "tenant_id": "tenant_default",
        "review_id": str(uuid4()),
        "pdf_minio_path": "",
        "pdf_local_path": temp_path,
        "raw_text": "",
        "page_count": 0,
        "structured": None,
        "dimension_scores": [],
        "weighted_score": 0.0,
        "issues": [],
        "summary": None,
        "fallback_used": False,
        "structured_output": None,
    }


async def run_benchmark(source: Path) -> None:
    fd, temp_path = tempfile.mkstemp(prefix="eduagent-resume-timing-", suffix=".pdf")
    os.close(fd)
    try:
        shutil.copy2(source, temp_path)
        state = build_initial_state(temp_path)
        with collect_timings() as timings:
            with timing_span("total"):
                with suppress_resume_node_logs():
                    state.update(await extract_text_node(state))
                    state.update(await extract_structured_node(state))
                    state.update(await run_six_dimensions_node(state))
                    state.update(await diagnose_issues_node(state))
                    state.update(await generate_summary_node(state))

        require_timings(timings, REQUIRED_TIMING_KEYS)
        print(format_timing_report(timings))
    finally:
        Path(temp_path).unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    asyncio.run(run_benchmark(args.file))


if __name__ == "__main__":
    main()
