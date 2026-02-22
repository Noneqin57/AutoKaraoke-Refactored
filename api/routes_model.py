# -*- coding: utf-8 -*-
"""
模型管理 API 路由 + WebSocket 下载进度
"""
import os
import time
import asyncio
import threading
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from config import ConfigManager
from core.model_manager import ModelManager, ModelDownloader, ModelInfo, ModelType
from api.schemas import ModelListResponse, ModelItem, ModelDownloadRequest
from api.ws_manager import model_ws_manager

router = APIRouter(prefix="/model", tags=["model"])

# 由 server.py 注入
_config_manager: ConfigManager = None
_model_manager: ModelManager = None

# 当前正在下载的任务
_active_downloads: dict = {}  # key -> ModelDownloader

# 模型列表缓存 (TTL 5秒，避免频繁磁盘扫描)
_model_list_cache = None
_model_list_cache_time = 0.0
_MODEL_LIST_CACHE_TTL = 5.0  # 秒


def init(config_manager: ConfigManager):
    """初始化路由模块"""
    global _config_manager, _model_manager
    _config_manager = config_manager
    model_dir = config_manager.get("MODEL_DIR") or os.path.join(os.getcwd(), "models")
    _model_manager = ModelManager(model_dir)


def _refresh_manager():
    """刷新模型管理器（路径可能变了）"""
    global _model_manager
    model_dir = _config_manager.get("MODEL_DIR") or os.path.join(os.getcwd(), "models")
    _model_manager = ModelManager(model_dir)


def _invalidate_cache():
    """使模型列表缓存失效"""
    global _model_list_cache_time
    _model_list_cache_time = 0.0


def _get_model_list_cached():
    """获取模型列表（带 TTL 缓存）"""
    global _model_list_cache, _model_list_cache_time
    now = time.monotonic()
    if _model_list_cache is not None and (now - _model_list_cache_time) < _MODEL_LIST_CACHE_TTL:
        return _model_list_cache
    _refresh_manager()
    _model_list_cache = _model_manager.get_model_list()
    _model_list_cache_time = now
    return _model_list_cache


@router.get("/list", response_model=ModelListResponse)
async def list_models():
    """获取所有可用模型（含下载状态）"""
    model_list = _get_model_list_cached()
    items = []
    for m in model_list:
        items.append(ModelItem(
            name=m.name,
            type=m.type,
            key=m.key,
            repo_id_or_url=m.repo_id_or_url,
            local_path=m.local_path,
            size_mb=m.size_mb,
            is_downloaded=m.is_downloaded
        ))
    return ModelListResponse(models=items)


@router.post("/download")
async def start_download(req: ModelDownloadRequest):
    """开始下载模型"""
    if req.key in _active_downloads:
        raise HTTPException(status_code=409, detail=f"模型 {req.key} 正在下载中")

    _invalidate_cache()
    _refresh_manager()
    model_list = _model_manager.get_model_list()

    # 查找目标模型
    target_model = None
    for m in model_list:
        if m.key == req.key and m.type == req.type:
            target_model = m
            break

    if not target_model:
        raise HTTPException(status_code=404, detail=f"未找到模型: {req.key} ({req.type})")

    if target_model.is_downloaded:
        raise HTTPException(status_code=400, detail="模型已下载")

    # 获取用于广播进度的事件循环
    loop = asyncio.get_event_loop()

    def progress_callback(percent: int, msg: str):
        """下载进度回调（在下载线程中调用）"""
        asyncio.run_coroutine_threadsafe(
            model_ws_manager.broadcast({
                "type": "download_progress",
                "model_key": req.key,
                "progress": percent,
                "message": msg
            }),
            loop
        )

    downloader = ModelDownloader(target_model, progress_callback=progress_callback)

    # 设置镜像
    mirror = _config_manager.get("HF_MIRROR", "https://hf-mirror.com")
    downloader.set_mirror(mirror)

    # 设置 SSL 验证
    if _config_manager.get("DISABLE_SSL_VERIFY", False):
        downloader.set_ssl_verify(True)

    _active_downloads[req.key] = downloader

    def run_download():
        try:
            downloader.start()
            _invalidate_cache()
            asyncio.run_coroutine_threadsafe(
                model_ws_manager.broadcast({
                    "type": "download_complete",
                    "model_key": req.key
                }),
                loop
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                model_ws_manager.broadcast({
                    "type": "download_error",
                    "model_key": req.key,
                    "message": str(e)
                }),
                loop
            )
        finally:
            _active_downloads.pop(req.key, None)

    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()

    return {"status": "downloading", "message": f"开始下载 {req.key}"}


@router.post("/download/stop")
async def stop_download(req: ModelDownloadRequest):
    """停止下载"""
    downloader = _active_downloads.get(req.key)
    if not downloader:
        raise HTTPException(status_code=404, detail="没有正在下载的任务")

    downloader.stop()
    _active_downloads.pop(req.key, None)
    return {"status": "stopped", "message": f"已停止下载 {req.key}"}


@router.delete("/{key}/{model_type}")
async def delete_model(key: str, model_type: str):
    """删除已下载的模型"""
    _invalidate_cache()
    _refresh_manager()
    model_list = _model_manager.get_model_list()

    target = None
    for m in model_list:
        if m.key == key and m.type == model_type:
            target = m
            break

    if not target:
        raise HTTPException(status_code=404, detail=f"未找到模型: {key}")

    if not target.is_downloaded:
        raise HTTPException(status_code=400, detail="模型未下载，无法删除")

    try:
        _model_manager.delete_model(target)
        _invalidate_cache()
        return {"status": "deleted", "message": f"已删除模型 {key}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.websocket("/ws")
async def model_websocket(websocket: WebSocket):
    """模型下载进度 WebSocket"""
    await model_ws_manager.connect(websocket)
    try:
        while True:
            # 保持连接，等待客户端消息（心跳）
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # 发送 ping 保活
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        model_ws_manager.disconnect(websocket)
    except Exception:
        model_ws_manager.disconnect(websocket)
