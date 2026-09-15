import logging

import pytest

from backend.agents.resume.timing import timing_span
from scripts.manual_tests import benchmark_resume_agent as benchmark


MARKER = "SENSITIVE_RESUME_MARKER"
NODES_LOGGER_NAME = "backend.agents.resume.nodes"


def _log_marker() -> None:
    logger = logging.getLogger(NODES_LOGGER_NAME)
    logger.debug(MARKER)
    logger.info(MARKER)
    logger.warning(MARKER)


def _install_safe_nodes(monkeypatch, *, raise_from_extract: bool = False):
    async def extract_text(state):
        _log_marker()
        with timing_span("extract_text"):
            if raise_from_extract:
                raise RuntimeError("benchmark boom")
            return {"raw_text": "synthetic", "page_count": 1}

    async def extract_structured(_state):
        _log_marker()
        with timing_span("extract_structured"):
            return {"structured": {}}

    async def run_six_dimensions(_state):
        _log_marker()
        with timing_span("six_dimensions"):
            for key in (
                "project_depth",
                "tech_match",
                "expression",
                "structure",
                "quantification",
                "authenticity",
            ):
                with timing_span(f"dimension.{key}"):
                    pass
        return {"dimension_scores": [], "weighted_score": 80.0}

    async def diagnose_issues(_state):
        _log_marker()
        with timing_span("diagnose_issues"):
            return {"issues": []}

    async def generate_summary(_state):
        _log_marker()
        with timing_span("generate_summary"):
            return {"summary": {}}

    monkeypatch.setattr(benchmark, "extract_text_node", extract_text)
    monkeypatch.setattr(benchmark, "extract_structured_node", extract_structured)
    monkeypatch.setattr(benchmark, "run_six_dimensions_node", run_six_dimensions)
    monkeypatch.setattr(benchmark, "diagnose_issues_node", diagnose_issues)
    monkeypatch.setattr(benchmark, "generate_summary_node", generate_summary)


@pytest.mark.asyncio
async def test_benchmark_suppresses_resume_node_markers_and_restores_logger(
    monkeypatch, tmp_path, caplog, capsys
):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-synthetic")
    logger = logging.getLogger(NODES_LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    _install_safe_nodes(monkeypatch)

    await benchmark.run_benchmark(source)

    assert MARKER not in caplog.text
    assert "Agent 总耗时" in capsys.readouterr().out
    assert logger.disabled is False


@pytest.mark.asyncio
async def test_benchmark_restores_logger_when_a_node_raises(monkeypatch, tmp_path):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-synthetic")
    logger = logging.getLogger(NODES_LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    _install_safe_nodes(monkeypatch, raise_from_extract=True)

    with pytest.raises(RuntimeError, match="benchmark boom"):
        await benchmark.run_benchmark(source)

    assert logger.disabled is False
