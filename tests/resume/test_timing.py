import asyncio

import pytest

from backend.agents.resume import timing
from backend.agents.resume.timing import (
    collect_timings,
    format_timing_report,
    require_timings,
    timed_stage,
    timing_span,
)


@pytest.mark.asyncio
async def test_timed_stage_preserves_result_and_records_timing():
    @timed_stage("example")
    async def example():
        return {"value": 7}

    with collect_timings() as timings:
        result = await example()

    assert result == {"value": 7}
    assert timings["example"] >= 0


@pytest.mark.asyncio
async def test_timed_stage_preserves_exception_and_records_timing():
    @timed_stage("failure")
    async def failure():
        raise RuntimeError("boom")

    with collect_timings() as timings:
        with pytest.raises(RuntimeError, match="boom"):
            await failure()

    assert timings["failure"] >= 0


@pytest.mark.asyncio
async def test_timing_spans_are_isolated_across_gathered_operations():
    async def operation(name):
        with timing_span(name):
            await asyncio.sleep(0)

    with collect_timings() as timings:
        await asyncio.gather(operation("a"), operation("b"))

    assert set(timings) == {"a", "b"}
    assert timings["a"] >= 0
    assert timings["b"] >= 0


@pytest.mark.asyncio
async def test_timed_stage_does_not_read_clock_outside_a_collector(monkeypatch):
    def fail_if_called():
        raise AssertionError("clock must not be read without a collector")

    monkeypatch.setattr(timing, "perf_counter_ns", fail_if_called)

    @timed_stage("disabled")
    async def example():
        return "unchanged"

    assert await example() == "unchanged"


@pytest.mark.asyncio
async def test_concurrent_collectors_keep_their_own_timings():
    both_collectors_entered = asyncio.Event()
    entered = []

    async def operation(name):
        with collect_timings() as timings:
            entered.append(name)
            if len(entered) == 2:
                both_collectors_entered.set()
            await both_collectors_entered.wait()
            with timing_span(name):
                await asyncio.sleep(0)
            return timings

    first, second = await asyncio.gather(operation("first"), operation("second"))

    assert set(first) == {"first"}
    assert set(second) == {"second"}


def test_nested_collector_restores_outer_collector_after_exception():
    with collect_timings() as outer:
        with pytest.raises(RuntimeError, match="inner boom"):
            with collect_timings() as inner:
                with timing_span("inner"):
                    raise RuntimeError("inner boom")
        with timing_span("outer"):
            pass

    assert set(inner) == {"inner"}
    assert set(outer) == {"outer"}


def test_require_timings_lists_missing_keys():
    with pytest.raises(RuntimeError, match="missing_b"):
        require_timings({"present": 1.0}, ["present", "missing_b"])


def test_require_timings_orders_all_missing_keys_deterministically():
    with pytest.raises(RuntimeError, match=r"Missing timings: alpha, beta"):
        require_timings({}, {"beta", "alpha"})


def test_format_timing_report_uses_chinese_labels_and_milliseconds():
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

    for label in (
        "简历文本提取",
        "六维度并行总耗时",
        "项目深度",
        "问题诊断",
        "问题总结",
        "Agent 总耗时",
        "最慢维度：简历结构",
        "24.00 ms",
    ):
        assert label in report


def test_format_timing_report_requires_all_timing_keys():
    with pytest.raises(RuntimeError, match="Missing timings: total"):
        format_timing_report(
            {
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
            }
        )
