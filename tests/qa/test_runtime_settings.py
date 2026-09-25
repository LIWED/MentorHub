from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.api.v1.settings as settings_api
from backend.api.v1.settings import require_admin
from backend.core.runtime_settings import (
    APISettingsPatch,
    QARetrievalSettingsPatch,
    RuntimeSettingsManager,
    RuntimeSettingsPatch,
)


def test_runtime_settings_persist_and_hide_api_keys(tmp_path):
    path = tmp_path / "runtime.json"
    manager = RuntimeSettingsManager(path)

    view = manager.update(
        RuntimeSettingsPatch(
            qa=QARetrievalSettingsPatch(
                recall_top_k_single=30,
                rerank_evidence_top_k=6,
                final_context_top_k=3,
            ),
            api=APISettingsPatch(
                llm_model="custom-model",
                deepseek_api_key="secret-deepseek-key",
                tavily_api_key="secret-tavily-key",
            ),
        )
    )

    assert view.qa.recall_top_k_single == 30
    assert view.api.llm_model == "custom-model"
    assert view.api.deepseek_api_key_configured is True
    assert view.api.tavily_api_key_configured is True

    public_json = view.model_dump_json()
    assert "secret-deepseek-key" not in public_json
    assert "secret-tavily-key" not in public_json

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["api"]["deepseek_api_key"] == "secret-deepseek-key"

    reloaded = RuntimeSettingsManager(path).get()
    assert reloaded.qa.recall_top_k_single == 30
    assert reloaded.api.deepseek_api_key == "secret-deepseek-key"


def test_runtime_settings_validate_top_k_relationships(tmp_path):
    manager = RuntimeSettingsManager(tmp_path / "runtime.json")

    with pytest.raises(ValidationError, match="最终上下文数量不能大于重排数量"):
        manager.update(
            RuntimeSettingsPatch(
                qa=QARetrievalSettingsPatch(
                    rerank_evidence_top_k=4,
                    final_context_top_k=5,
                )
            )
        )


def test_runtime_settings_reset_restores_defaults(tmp_path):
    path = tmp_path / "runtime.json"
    manager = RuntimeSettingsManager(path)
    manager.update(
        RuntimeSettingsPatch(
            qa=QARetrievalSettingsPatch(recall_top_k_single=40)
        )
    )
    assert path.exists()

    view = manager.reset()

    assert not path.exists()
    assert view.qa.recall_top_k_single == 20


def test_system_settings_are_admin_only():
    assert require_admin({"role": "admin"})["role"] == "admin"

    with pytest.raises(HTTPException) as exc:
        require_admin({"role": "student"})

    assert exc.value.status_code == 403


def test_settings_http_never_returns_plaintext_secret(tmp_path, monkeypatch):
    manager = RuntimeSettingsManager(tmp_path / "runtime.json")
    monkeypatch.setattr(settings_api, "get_runtime_settings_manager", lambda: manager)
    monkeypatch.setattr(settings_api.LLMFactory, "clear_cache", lambda: None)

    app = FastAPI()
    app.include_router(settings_api.router, prefix="/settings")
    app.dependency_overrides[settings_api.require_admin] = lambda: {
        "role": "admin",
        "user_id": "admin",
    }
    client = TestClient(app)

    response = client.patch(
        "/settings",
        json={
            "qa": {"recall_top_k_single": 28},
            "api": {"deepseek_api_key": "http-secret-key"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["qa"]["recall_top_k_single"] == 28
    assert body["api"]["deepseek_api_key_configured"] is True
    assert "http-secret-key" not in response.text
    assert "deepseek_api_key" not in body["api"]


def test_settings_http_rejects_invalid_top_k_relationship(tmp_path, monkeypatch):
    manager = RuntimeSettingsManager(tmp_path / "runtime.json")
    monkeypatch.setattr(settings_api, "get_runtime_settings_manager", lambda: manager)

    app = FastAPI()
    app.include_router(settings_api.router, prefix="/settings")
    app.dependency_overrides[settings_api.require_admin] = lambda: {"role": "admin"}
    client = TestClient(app)

    response = client.patch(
        "/settings",
        json={
            "qa": {
                "rerank_evidence_top_k": 4,
                "final_context_top_k": 5,
            }
        },
    )

    assert response.status_code == 422
