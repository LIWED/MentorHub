# Resume Agent Timing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in, console-only wall-clock timing for the real resume review Agent stages and a safe manual benchmark that runs the real PDF and LLM pipeline without changing business outputs or writing the database.

**Architecture:** A `ContextVar`-backed collector is inactive during normal production execution and is enabled only by the benchmark. Async decorators time graph nodes, while a nested span records each concurrent dimension. The benchmark copies the input PDF to a temporary file, calls the existing production nodes in graph order through summary generation, validates the timing contract, and prints a report.

**Tech Stack:** Python 3.11, asyncio, contextvars, time.perf_counter_ns, pytest, pytest-asyncio, existing LangGraph resume nodes.

## Global Constraints

- Do not change prompts, LLM selection, retry counts, retry sleeps, fallback behavior, scoring weights, concurrency, graph edges, API responses, database schema, or frontend code.
- Timing is opt-in and console-only; do not persist it in `ResumeState`, PostgreSQL, files, or API responses.
- Use `time.perf_counter_ns()` and display milliseconds with two decimals.
- Stage timings include prompt construction, LLM calls, parsing, retries, and retry waits.
- The benchmark must use real PDF parsing and real configured LLM calls; automated unit tests may use fakes only to avoid network calls.
- Never read or print `.env.local`, API keys, login tokens, resume text, or structured resume contents.
- Copy the source PDF before execution and always remove only the exact temporary copy.
- Do not call `save_results_node`; the benchmark must not write or delete database records.
- The checkout is not a Git repository, so commit steps are documented as skipped rather than executed.

---

## File Structure

- Create `backend/agents/resume/timing.py`: isolated timing collector, span, async decorator, and required-key validation.
- Modify `backend/agents/resume/nodes.py`: apply stage decorators and a per-dimension span only.
- Create `tests/resume/test_timing.py`: unit contract for the timing collector and concurrency behavior.
- Create `tests/resume/test_nodes_timing.py`: offline integration tests for node timing wiring and unchanged outputs.
- Create `scripts/manual_tests/benchmark_resume_agent.py`: real console benchmark using an input PDF and production nodes.
- Create/update `docs/PROJECT.md`, `docs/CHANGELOG.md`, and `docs/BUGS.md`: concise project status required by repository instructions.

### Task 1: Timing collector contract

**Files:**
- Create: `tests/resume/test_timing.py`
- Create: `backend/agents/resume/timing.py`

**Interfaces:**
- Produces: `collect_timings() -> Iterator[dict[str, float]]`
- Produces: `timing_span(name: str) -> ContextManager[None]`
- Produces: `timed_stage(name: str) -> Callable[[AsyncCallable], AsyncCallable]`
- Produces: `require_timings(timings: Mapping[str, float], required: Iterable[str]) -> None`

- [ ] **Step 1: Write the failing collector tests**

```python
import asyncio

import pytest

from backend.agents.resume.timing import (
    collect_timings,
    require_timings,
    timed_stage,
    timing_span,
)


@pytest.mark.asyncio
async def test_timed_stage_preserves_result_and_records_elapsed_time():
    @timed_stage("example")
    async def operation():
        await asyncio.sleep(0)
        return {"value": 7}

    with collect_timings() as timings:
        result = await operation()

    assert result == {"value": 7}
    assert timings["example"] >= 0


@pytest.mark.asyncio
async def test_timed_stage_preserves_exception_and_records_elapsed_time():
    @timed_stage("failure")
    async def operation():
        raise RuntimeError("boom")

    with collect_timings() as timings:
        with pytest.raises(RuntimeError, match="boom"):
            await operation()

    assert timings["failure"] >= 0


@pytest.mark.asyncio
async def test_concurrent_spans_record_distinct_names():
    async def operation(name: str):
        with timing_span(name):
            await asyncio.sleep(0)

    with collect_timings() as timings:
        await asyncio.gather(operation("a"), operation("b"))

    assert set(timings) == {"a", "b"}
    assert all(value >= 0 for value in timings.values())


def test_require_timings_reports_missing_names():
    with pytest.raises(RuntimeError, match="missing_b"):
        require_timings({"present": 1.0}, ["present", "missing_b"])
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume/test_timing.py -v
```

Expected: collection fails because `backend.agents.resume.timing` does not exist.

- [ ] **Step 3: Implement the minimal collector**

```python
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter_ns
from typing import Any, TypeVar

_CURRENT_TIMINGS: ContextVar[dict[str, float] | None] = ContextVar(
    "resume_agent_timings", default=None
)
_F = TypeVar("_F", bound=Callable[..., Any])


@contextmanager
def collect_timings() -> Iterator[dict[str, float]]:
    timings: dict[str, float] = {}
    token = _CURRENT_TIMINGS.set(timings)
    try:
        yield timings
    finally:
        _CURRENT_TIMINGS.reset(token)


@contextmanager
def timing_span(name: str) -> Iterator[None]:
    timings = _CURRENT_TIMINGS.get()
    if timings is None:
        yield
        return
    started_ns = perf_counter_ns()
    try:
        yield
    finally:
        timings[name] = (perf_counter_ns() - started_ns) / 1_000_000


def timed_stage(name: str):
    def decorate(func: _F) -> _F:
        @wraps(func)
        async def wrapped(*args, **kwargs):
            with timing_span(name):
                return await func(*args, **kwargs)
        return wrapped
    return decorate


def require_timings(timings: Mapping[str, float], required: Iterable[str]) -> None:
    missing = [name for name in required if name not in timings]
    if missing:
        raise RuntimeError("Missing timing entries: " + ", ".join(missing))
```

Remove unused imports before saving so lint and import output remain clean.

- [ ] **Step 4: Run the collector tests and verify GREEN**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume/test_timing.py -v
```

Expected: all collector contract tests pass.

- [ ] **Step 5: Record checkpoint**

Git commit is skipped because `F:\mygit\EduAgent` has no `.git` repository. Record completed checkboxes in this plan instead.

### Task 2: Resume node timing wiring

**Files:**
- Create: `tests/resume/test_nodes_timing.py`
- Modify: `backend/agents/resume/nodes.py:3-18,93,142,210-246,276,334`

**Interfaces:**
- Consumes: `timed_stage(name)` and `timing_span(name)` from Task 1.
- Produces: the existing node functions with exactly the same arguments, async behavior, return dictionaries, retry behavior, and exceptions.
- Produces timing keys: `extract_text`, `extract_structured`, `six_dimensions`, six `dimension.<key>` entries, `diagnose_issues`, and `generate_summary`.

- [ ] **Step 1: Write failing node-wiring tests**

```python
import pytest

from backend.agents.resume import nodes
from backend.agents.resume.state import DimensionScore
from backend.agents.resume.timing import collect_timings


@pytest.mark.asyncio
async def test_extract_text_keeps_output_and_records_stage(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "_sync_extract_text",
        lambda _path: {"raw_text": "真实文本" * 100, "page_count": 2},
    )
    state = {"pdf_local_path": "unused.pdf"}

    with collect_timings() as timings:
        result = await nodes.extract_text_node(state)

    assert result == {"raw_text": "真实文本" * 100, "page_count": 2}
    assert timings["extract_text"] >= 0


@pytest.mark.asyncio
async def test_six_dimensions_keep_scores_and_record_each_dimension(monkeypatch):
    class FakeStructuredLLM:
        async def ainvoke(self, _messages):
            return DimensionScore(score=80, issues=[], suggestions=[])

    monkeypatch.setattr(nodes, "get_structured_llm", lambda *_args, **_kwargs: FakeStructuredLLM())
    state = {"raw_text": "resume", "structured": {}}

    with collect_timings() as timings:
        result = await nodes.run_six_dimensions_node(state)

    assert len(result["dimension_scores"]) == 6
    assert result["weighted_score"] == 80.0
    assert timings["six_dimensions"] >= 0
    assert {
        "dimension.project_depth",
        "dimension.tech_match",
        "dimension.expression",
        "dimension.structure",
        "dimension.quantification",
        "dimension.authenticity",
    }.issubset(timings)
```

- [ ] **Step 2: Run the node tests and verify RED**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume/test_nodes_timing.py -v
```

Expected: assertions fail because the production nodes have not recorded timing keys.

- [ ] **Step 3: Add only timing imports and decorators**

Add:

```python
from backend.agents.resume.timing import timed_stage, timing_span
```

Apply these exact decorator insertions:

```diff
+@timed_stage("extract_text")
 async def extract_text_node(state: ResumeState) -> dict:

+@timed_stage("extract_structured")
 async def extract_structured_node(state: ResumeState) -> dict:

+@timed_stage("six_dimensions")
 async def run_six_dimensions_node(state: ResumeState) -> dict:

+@timed_stage("diagnose_issues")
 async def diagnose_issues_node(state: ResumeState) -> dict:

+@timed_stage("generate_summary")
 async def generate_summary_node(state: ResumeState) -> dict:
```

Replace only the nested `review_one_dimension(dim)` body with the same statements inside the timing span:

```python
async def review_one_dimension(dim: dict) -> dict:
    with timing_span(f"dimension.{dim['key']}"):
        prompt_template = DIMENSION_REVIEW_PROMPTS.get(dim["key"], "")
        if not prompt_template:
            return _empty_dimension_score(dim)
        prompt = prompt_template.format(
            resume_text=raw_text[:3000],
            structured_summary=structured_summary,
            focus=dim["focus"],
        )
        for attempt in range(2):
            try:
                structured_llm = get_structured_llm("resume", DimensionScore)
                result: DimensionScore = await structured_llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                score = result.model_dump()
                score["dimension"] = dim["name"]
                score["weight"] = dim["weight"]
                score["key"] = dim["key"]
                return score
            except Exception as exc:
                if attempt == 0:
                    logger.warning(
                        "six_dimensions.dimension_retry",
                        dimension=dim["name"],
                        error=str(exc),
                    )
                    await asyncio.sleep(1)
                else:
                    logger.warning(
                        "six_dimensions.dimension_failed",
                        dimension=dim["name"],
                        error=str(exc),
                    )
                    return _empty_dimension_score(dim)
```

- [ ] **Step 4: Run node-wiring and collector tests**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume/test_timing.py tests/resume/test_nodes_timing.py -v
```

Expected: all tests pass; six dimension scores remain ordered as `SIX_DIMENSIONS` defines them.

- [ ] **Step 5: Record checkpoint**

Git commit is skipped because the checkout is non-Git. Confirm only `nodes.py` changed among existing production files.

### Task 3: Real console benchmark

**Files:**
- Create: `scripts/manual_tests/benchmark_resume_agent.py`
- Modify: `tests/resume/test_timing.py`

**Interfaces:**
- Consumes: `collect_timings()`, `timing_span("total")`, `require_timings()`.
- Consumes production nodes: `extract_text_node`, `extract_structured_node`, `run_six_dimensions_node`, `diagnose_issues_node`, `generate_summary_node`.
- Produces CLI: `python scripts/manual_tests/benchmark_resume_agent.py [--file <pdf>]`.
- Produces console-only timing report; no result file or database record.

- [ ] **Step 1: Add a failing report-contract test**

Add to `tests/resume/test_timing.py` after exposing `format_timing_report()` from the timing module:

```python
from backend.agents.resume.timing import format_timing_report


def test_format_timing_report_contains_requested_sections():
    timings = {
        "extract_text": 1.0,
        "extract_structured": 2.0,
        "six_dimensions": 6.0,
        "dimension.project_depth": 3.0,
        "dimension.tech_match": 4.0,
        "dimension.expression": 5.0,
        "dimension.structure": 6.0,
        "dimension.quantification": 2.5,
        "dimension.authenticity": 1.5,
        "diagnose_issues": 7.0,
        "generate_summary": 8.0,
        "total": 24.0,
    }
    report = format_timing_report(timings)

    assert "简历文本提取" in report
    assert "六维度并行总耗时" in report
    assert "项目深度" in report
    assert "问题诊断" in report
    assert "问题总结" in report
    assert "Agent 总耗时" in report
    assert "最慢维度：简历结构" in report
```

- [ ] **Step 2: Run the report test and verify RED**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume/test_timing.py::test_format_timing_report_contains_requested_sections -v
```

Expected: import fails because `format_timing_report` is not implemented.

- [ ] **Step 3: Implement deterministic report formatting**

Add fixed Chinese labels and format every duration with `:,.2f` milliseconds. Determine the slowest dimension with `max(dimension_items, key=lambda item: item[1])`. Formatting must not print resume data, scores, prompts, or credentials.

- [ ] **Step 4: Implement the manual benchmark**

The benchmark must:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = PROJECT_ROOT / "samples" / "sample1.pdf"
```

Then:

1. Validate that the selected path exists, is a file, and ends in `.pdf`.
2. Create an exact temporary PDF path using `tempfile.mkstemp(suffix=".pdf", prefix="eduagent-resume-timing-")`.
3. Close the returned file descriptor and copy the selected PDF with `shutil.copy2`.
4. Build the same state fields needed by the five production nodes, using generated UUID strings and no real user identity.
5. Enter `collect_timings()`, then `timing_span("total")`.
6. Invoke the five nodes in graph order and `state.update(result)` after each call.
7. Verify all twelve required timing keys with `require_timings()`.
8. Print `format_timing_report(timings)` only.
9. In `finally`, remove only the created temporary PDF with `Path.unlink(missing_ok=True)`.

- [ ] **Step 5: Run offline checks for the benchmark module**

Run:

```powershell
conda run -n EduAgent python scripts/manual_tests/benchmark_resume_agent.py --help
conda run -n EduAgent python -m compileall -q backend/agents/resume scripts/manual_tests/benchmark_resume_agent.py tests/resume
```

Expected: help exits with code 0 and compilation emits no errors.

- [ ] **Step 6: Run the complete automated suite for this change**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume -v
```

Expected: all timing tests pass without network or database access.

- [ ] **Step 7: Record checkpoint**

Git commit is skipped because the checkout is non-Git. Record the exact passing test count in the final report.

### Task 4: Real benchmark and project records

**Files:**
- Create/update: `docs/PROJECT.md`
- Create/update: `docs/CHANGELOG.md`
- Create/update: `docs/BUGS.md`
- Verify: `scripts/manual_tests/benchmark_resume_agent.py`

**Interfaces:**
- Consumes: the configured local model and DeepSeek credentials through existing project configuration.
- Produces: one console timing report from `samples/sample1.pdf`.
- Produces: concise project status records under 200 lines each.

- [ ] **Step 1: Run the real benchmark once**

Run:

```powershell
conda run -n EduAgent python scripts/manual_tests/benchmark_resume_agent.py
```

Expected: all requested stages and six dimensions are printed with non-negative milliseconds. The run may consume configured LLM API quota.

- [ ] **Step 2: Inspect behavior-preservation evidence**

Confirm:

- Exactly six `dimension.*` timing entries exist.
- `six_dimensions` is a wall-clock duration and is not calculated as the sum of dimension durations.
- The benchmark leaves `samples/sample1.pdf` present and unchanged.
- No database row is inserted because `save_results_node` is never called.
- No timing fields appear in API schemas or `ResumeState`.

- [ ] **Step 3: Update project records**

`docs/PROJECT.md` records the feature status, how to run the benchmark, and that timings are console-only. `docs/CHANGELOG.md` records the timing collector, node spans, benchmark, and tests. `docs/BUGS.md` records that no business bug was fixed and notes the existing risk that live timing depends on LLM/network latency; do not claim deterministic performance.

- [ ] **Step 4: Run final regression checks**

Run:

```powershell
conda run -n EduAgent python -m pytest tests/resume -v
conda run -n EduAgent python -m compileall -q backend/agents/resume scripts/manual_tests/benchmark_resume_agent.py tests/resume
```

Expected: all tests pass and compilation exits with code 0.

- [ ] **Step 5: Record final checkpoint**

Git commit is unavailable. Report all created and modified files, test results, the observed real timing table, and any external-service failures without claiming unverified success.
