# -*- coding: utf-8 -*-
"""
FastAPI 应用工厂

- lifespan 管理 daemon worker 进程
- 挂载所有 API 路由到 /api/ 前缀
- 托管前端静态文件（web/dist/）
- SPA catch-all 路由
"""
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from multiprocessing import Process, Queue, Event

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import ConfigManager
from core.whisper_worker import daemon_worker

from api import routes_config, routes_file, routes_audio, routes_task, routes_model, routes_msst, routes_batch
from api.routes_file import cleanup_uploaded_files


def _get_static_dir() -> str:
    """获取前端静态文件目录，兼容 PyInstaller 打包"""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "web", "dist")
    return os.path.join(os.path.dirname(__file__), "web", "dist")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""

    # === 共享状态 ===
    config_manager = ConfigManager()
    task_queue = Queue()
    result_queue = Queue()
    progress_queue = Queue()
    stop_event = Event()
    worker_process = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        nonlocal worker_process

        # 将共享状态存储到 app.state，供路由模块通过依赖注入访问
        app.state.config_manager = config_manager
        app.state.task_queue = task_queue
        app.state.result_queue = result_queue
        app.state.progress_queue = progress_queue
        app.state.stop_event = stop_event

        # 启动 daemon worker 进程
        worker_process = Process(
            target=daemon_worker,
            args=(task_queue, result_queue, progress_queue, stop_event),
            daemon=True
        )
        worker_process.start()
        print(f"🚀 Daemon worker started (PID: {worker_process.pid})")

        yield  # 应用运行中

        # 关闭 worker
        print("🛑 Shutting down daemon worker...")
        task_queue.put("EXIT")
        if worker_process.is_alive():
            worker_process.join(timeout=3)
            if worker_process.is_alive():
                worker_process.terminate()
        print("✅ Daemon worker stopped")

        # 清理上传的临时文件
        cleanup_uploaded_files()
        print("✅ Uploaded files cleaned")

    app = FastAPI(
        title="REATK - AutoKaraoke Refactored",
        version="2.0.0",
        description="基于 Whisper 的逐字歌词生成器 (Web 版)",
        lifespan=lifespan
    )

    # === CORS（开发模式下前端 Vite 在不同端口） ===
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === 初始化路由模块（保留向后兼容的 init 调用） ===
    routes_config.init(config_manager)
    routes_task.init(task_queue, result_queue, progress_queue, stop_event, config_manager)
    routes_model.init(config_manager)
    routes_msst.init(config_manager)
    routes_batch.init(task_queue, result_queue, progress_queue, stop_event, config_manager)

    # === 注册路由 ===
    app.include_router(routes_config.router, prefix="/api")
    app.include_router(routes_file.router, prefix="/api")
    app.include_router(routes_audio.router, prefix="/api")
    app.include_router(routes_task.router, prefix="/api")
    app.include_router(routes_model.router, prefix="/api")
    app.include_router(routes_msst.router, prefix="/api")
    app.include_router(routes_batch.router, prefix="/api")

    # === 托管前端静态文件 ===
    static_dir = _get_static_dir()
    if os.path.exists(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

        @app.get("/")
        async def serve_index():
            return FileResponse(os.path.join(static_dir, "index.html"))

        # SPA catch-all：非 /api 和 /assets 的路由都返回 index.html
        @app.get("/{full_path:path}")
        async def spa_catch_all(full_path: str):
            # 排除 API 路由，不应由 SPA 处理
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            # 尝试返回静态文件
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            # 返回 index.html（SPA 路由）
            return FileResponse(os.path.join(static_dir, "index.html"))
    else:
        @app.get("/")
        async def dev_message():
            return {
                "message": "REATK Web API 运行中",
                "note": "前端尚未构建。开发时请运行 'cd web && npm run dev'",
                "docs": "/docs"
            }

    return app
