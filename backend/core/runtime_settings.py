from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SETTINGS_PATH = PROJECT_ROOT / ".runtime_settings.json"


class QARetrievalSettings(BaseModel):
    """QA 检索链可在运行时调整的参数。"""

    recall_top_k_single: int = Field(default=20, ge=1, le=200)
    recall_top_k_hyde: int = Field(default=20, ge=1, le=200)
    recall_top_k_broad_per: int = Field(default=10, ge=1, le=100)
    recall_top_k_iterative: int = Field(default=12, ge=1, le=100)
    rerank_evidence_top_k: int = Field(default=6, ge=1, le=50)
    final_context_top_k: int = Field(default=3, ge=1, le=20)
    retrieval_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_gap_queries: int = Field(default=2, ge=1, le=10)
    max_gap_rounds: int = Field(default=2, ge=0, le=10)

    @model_validator(mode="after")
    def validate_top_k_order(self) -> "QARetrievalSettings":
        recalls = (
            self.recall_top_k_single,
            self.recall_top_k_hyde,
            self.recall_top_k_broad_per,
            self.recall_top_k_iterative,
        )
        if self.rerank_evidence_top_k > min(recalls):
            raise ValueError("重排数量不能大于任一召回数量")
        if self.final_context_top_k > self.rerank_evidence_top_k:
            raise ValueError("最终上下文数量不能大于重排数量")
        return self


class APISettings(BaseModel):
    """实际生效的 API 配置。密钥只在后端内存/本地覆盖文件中存在。"""

    llm_base_url: str = Field(min_length=1, max_length=500)
    llm_model: str = Field(min_length=1, max_length=200)
    deepseek_api_key: str = ""
    web_search_provider: Literal["auto", "tavily", "duckduckgo"] = "auto"
    tavily_api_key: str = ""


class RuntimeSettings(BaseModel):
    qa: QARetrievalSettings = Field(default_factory=QARetrievalSettings)
    api: APISettings


class QARetrievalSettingsPatch(BaseModel):
    recall_top_k_single: int | None = Field(default=None, ge=1, le=200)
    recall_top_k_hyde: int | None = Field(default=None, ge=1, le=200)
    recall_top_k_broad_per: int | None = Field(default=None, ge=1, le=100)
    recall_top_k_iterative: int | None = Field(default=None, ge=1, le=100)
    rerank_evidence_top_k: int | None = Field(default=None, ge=1, le=50)
    final_context_top_k: int | None = Field(default=None, ge=1, le=20)
    retrieval_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    max_gap_queries: int | None = Field(default=None, ge=1, le=10)
    max_gap_rounds: int | None = Field(default=None, ge=0, le=10)


class APISettingsPatch(BaseModel):
    llm_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)
    deepseek_api_key: str | None = Field(default=None, max_length=1000)
    web_search_provider: Literal["auto", "tavily", "duckduckgo"] | None = None
    tavily_api_key: str | None = Field(default=None, max_length=1000)


class RuntimeSettingsPatch(BaseModel):
    qa: QARetrievalSettingsPatch | None = None
    api: APISettingsPatch | None = None


class APISettingsView(BaseModel):
    llm_base_url: str
    llm_model: str
    web_search_provider: Literal["auto", "tavily", "duckduckgo"]
    deepseek_api_key_configured: bool
    tavily_api_key_configured: bool


class RuntimeSettingsView(BaseModel):
    qa: QARetrievalSettings
    api: APISettingsView


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class RuntimeSettingsManager:
    """
    运行时设置管理器。

    .env.local 仍是基础配置；.runtime_settings.json 只保存前端设置页产生的覆盖值。
    这样既不修改用户原有 .env.local，也不会把密钥写进 Git。
    """

    def __init__(self, path: Path | str = RUNTIME_SETTINGS_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._current: RuntimeSettings | None = None

    def _base_settings_dict(self) -> dict:
        env = get_settings()
        return {
            "qa": QARetrievalSettings().model_dump(),
            "api": {
                "llm_base_url": env.deepseek_base_url,
                # 保持当前项目 llm_factory 原先实际使用的模型名不变。
                "llm_model": "deepseek-v4-flash-vision-exp",
                "deepseek_api_key": env.deepseek_api_key,
                "web_search_provider": "auto",
                "tavily_api_key": env.tavily_api_key,
            },
        }

    def _read_overrides(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("runtime settings root must be an object")
            return raw
        except Exception as exc:
            logger.error("runtime_settings.read_failed", path=str(self.path), error=str(exc))
            raise RuntimeError("运行设置文件损坏，无法读取") from exc

    def _build_effective(self, overrides: dict) -> RuntimeSettings:
        return RuntimeSettings.model_validate(
            _deep_merge(self._base_settings_dict(), overrides)
        )

    def get(self) -> RuntimeSettings:
        with self._lock:
            if self._current is None:
                self._current = self._build_effective(self._read_overrides())
            return self._current

    def public_view(self) -> RuntimeSettingsView:
        current = self.get()
        return RuntimeSettingsView(
            qa=current.qa,
            api=APISettingsView(
                llm_base_url=current.api.llm_base_url,
                llm_model=current.api.llm_model,
                web_search_provider=current.api.web_search_provider,
                deepseek_api_key_configured=bool(current.api.deepseek_api_key),
                tavily_api_key_configured=bool(current.api.tavily_api_key),
            ),
        )

    def update(self, patch: RuntimeSettingsPatch) -> RuntimeSettingsView:
        """
        合并更新。None 表示“不修改”；空字符串可显式清空 API Key。
        更新前先用完整 RuntimeSettings 校验跨字段关系，校验失败不会写文件。
        """
        with self._lock:
            overrides = self._read_overrides()
            patch_dict = patch.model_dump(exclude_unset=True, exclude_none=True)
            merged_overrides = _deep_merge(overrides, patch_dict)
            effective = self._build_effective(merged_overrides)
            self._write_overrides(merged_overrides)
            self._current = effective
            logger.info(
                "runtime_settings.updated",
                qa_changed=bool(patch_dict.get("qa")),
                api_changed=bool(patch_dict.get("api")),
            )
            return self.public_view()

    def reset(self) -> RuntimeSettingsView:
        """删除运行时覆盖，恢复 .env.local + 代码默认值。"""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            self._current = self._build_effective({})
            logger.info("runtime_settings.reset")
            return self.public_view()

    def _write_overrides(self, overrides: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(overrides, ensure_ascii=False, indent=2)
        tmp_path.write_text(payload + os.linesep, encoding="utf-8")
        os.replace(tmp_path, self.path)


_MANAGER = RuntimeSettingsManager()


def get_runtime_settings() -> RuntimeSettings:
    return _MANAGER.get()


def get_runtime_settings_manager() -> RuntimeSettingsManager:
    return _MANAGER
