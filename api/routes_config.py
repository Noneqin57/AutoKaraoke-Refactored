# -*- coding: utf-8 -*-
"""配置 CRUD API 路由"""
from fastapi import APIRouter

from config import ConfigManager, LANGUAGES, PROMPT_DEFAULTS
from api.schemas import ConfigResponse, ConfigUpdateRequest, LanguagesResponse, LanguageItem

router = APIRouter(prefix="/config", tags=["config"])

# 全局配置管理器实例（由 server.py 注入）
_config_manager: ConfigManager = None


def init(config_manager: ConfigManager):
    """初始化路由模块的配置管理器引用"""
    global _config_manager
    _config_manager = config_manager


@router.get("", response_model=ConfigResponse)
async def get_config():
    """获取全部配置"""
    return ConfigResponse(config=_config_manager.config.copy())


@router.put("", response_model=ConfigResponse)
async def update_config(req: ConfigUpdateRequest):
    """部分更新配置"""
    _config_manager.update_and_save(req.updates)
    return ConfigResponse(config=_config_manager.config.copy())


@router.get("/languages", response_model=LanguagesResponse)
async def get_languages():
    """获取支持的语言列表"""
    items = [LanguageItem(code=code, name=name) for code, name in LANGUAGES.items()]
    return LanguagesResponse(languages=items)


@router.get("/prompt_defaults")
async def get_prompt_defaults():
    """获取各语言的默认提示词"""
    return PROMPT_DEFAULTS
