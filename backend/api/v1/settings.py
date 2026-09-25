from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from backend.core.llm_factory import LLMFactory
from backend.core.runtime_settings import (
    RuntimeSettingsPatch,
    RuntimeSettingsView,
    get_runtime_settings_manager,
)
from backend.dependencies import get_current_user

router = APIRouter()


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可以修改系统设置",
        )
    return current_user


@router.get("", response_model=RuntimeSettingsView)
async def get_system_settings(_: dict = Depends(require_admin)) -> RuntimeSettingsView:
    return get_runtime_settings_manager().public_view()


@router.patch("", response_model=RuntimeSettingsView)
async def update_system_settings(
    payload: RuntimeSettingsPatch,
    _: dict = Depends(require_admin),
) -> RuntimeSettingsView:
    try:
        view = get_runtime_settings_manager().update(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_context=False),
        ) from exc
    # API endpoint / model / key 改动后，必须丢弃已有 LLM 实例缓存，
    # 下一个请求才会使用新配置。
    if payload.api is not None:
        LLMFactory.clear_cache()
    return view


@router.delete("", response_model=RuntimeSettingsView)
async def reset_system_settings(_: dict = Depends(require_admin)) -> RuntimeSettingsView:
    view = get_runtime_settings_manager().reset()
    LLMFactory.clear_cache()
    return view
