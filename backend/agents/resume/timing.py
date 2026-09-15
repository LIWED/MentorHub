from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter_ns
from typing import ContextManager, Iterable, Iterator, Mapping


_timings: ContextVar[dict[str, float] | None] = ContextVar("resume_timings", default=None)


REQUIRED_TIMING_KEYS = (
    "extract_text",
    "extract_structured",
    "six_dimensions",
    "dimension.project_depth",
    "dimension.tech_match",
    "dimension.expression",
    "dimension.structure",
    "dimension.quantification",
    "dimension.authenticity",
    "diagnose_issues",
    "generate_summary",
    "total",
)

STAGE_LABELS = (
    ("extract_text", "简历文本提取"),
    ("extract_structured", "简历结构化提取"),
    ("six_dimensions", "六维度并行总耗时"),
)

DIMENSION_LABELS = (
    ("dimension.project_depth", "项目深度"),
    ("dimension.tech_match", "技术匹配度"),
    ("dimension.expression", "表达规范性"),
    ("dimension.structure", "简历结构"),
    ("dimension.quantification", "量化程度"),
    ("dimension.authenticity", "真实可信度"),
)

ENDING_LABELS = (
    ("diagnose_issues", "问题诊断"),
    ("generate_summary", "问题总结"),
)


@contextmanager
def collect_timings() -> Iterator[dict[str, float]]:
    timings: dict[str, float] = {}
    token = _timings.set(timings)
    try:
        yield timings
    finally:
        _timings.reset(token)


@contextmanager
def timing_span(name: str) -> ContextManager[None]:
    timings = _timings.get()
    if timings is None:
        yield
        return

    started_ns = perf_counter_ns()
    try:
        yield
    finally:
        timings[name] = (perf_counter_ns() - started_ns) / 1_000_000


def timed_stage(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            with timing_span(name):
                return await func(*args, **kwargs)

        return wrapped

    return decorator


def require_timings(timings: Mapping[str, float], required: Iterable[str]) -> None:
    missing = sorted(name for name in required if name not in timings)
    if missing:
        raise RuntimeError(f"Missing timings: {', '.join(missing)}")


def format_timing_report(timings: Mapping[str, float]) -> str:
    require_timings(timings, REQUIRED_TIMING_KEYS)

    lines = ["简历 Agent 计时报告"]
    for key, label in STAGE_LABELS:
        lines.append(f"{label}：{timings[key]:,.2f} ms")
    for key, label in DIMENSION_LABELS:
        lines.append(f"{label}：{timings[key]:,.2f} ms")

    slowest_key, slowest_label = max(
        DIMENSION_LABELS,
        key=lambda item: timings[item[0]],
    )
    lines.append(f"最慢维度：{slowest_label}（{timings[slowest_key]:,.2f} ms）")

    for key, label in ENDING_LABELS:
        lines.append(f"{label}：{timings[key]:,.2f} ms")
    lines.append(f"Agent 总耗时：{timings['total']:,.2f} ms")
    return "\n".join(lines)
