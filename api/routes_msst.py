# -*- coding: utf-8 -*-
"""
人声分离模型管理 API 路由

使用 audio-separator 库，模型自动管理，只需提供列表接口。
"""
from fastapi import APIRouter

from config import ConfigManager
from core.msst_separator import get_available_models
from api.schemas import MsstModelListResponse, MsstModelItem

router = APIRouter(prefix="/msst", tags=["msst"])

# 由 server.py 注入
_config_manager: ConfigManager = None


def init(config_manager: ConfigManager):
    """初始化路由模块"""
    global _config_manager
    _config_manager = config_manager


@router.get("/list", response_model=MsstModelListResponse)
async def list_msst_models():
    """获取所有可用的人声分离模型"""
    models = get_available_models()
    items = [
        MsstModelItem(
            key=m["key"],
            name=m["name"],
            model_type="onnx",
            size_mb=m["size_mb"],
            is_downloaded=m["is_downloaded"],
        )
        for m in models
    ]
    return MsstModelListResponse(models=items)
