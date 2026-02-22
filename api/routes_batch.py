# -*- coding: utf-8 -*-
"""
批量生成任务 API 路由 + WebSocket 进度

设计要点：
- 复用现有 daemon_worker 的串行队列机制
- 逐个提交任务，等待完成后再提交下一个
- 通过 WebSocket 广播每个子任务的进度
"""
import os
import io
import zipfile
import asyncio
import threading
from queue import Empty
from multiprocessing import Queue, Event
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from core.lrc_parser import LrcParser
from core.whisper_worker import WorkerArgs
from config import ConfigManager
from api.schemas import BatchStartRequest, BatchStartResponse
from api.ws_manager import batch_ws_manager
from api.routes_file import get_uploaded_filepath

router = APIRouter(prefix="/batch", tags=["batch"])

# 由 server.py 注入
_task_queue: Queue = None
_result_queue: Queue = None
_progress_queue: Queue = None
_stop_event: Event = None
_config_manager: ConfigManager = None

# 批量任务状态
_batch_running = False
_batch_lock = asyncio.Lock()
_batch_results: list = []  # [{name, status, result, error}]
_batch_task: asyncio.Task = None


def init(task_queue: Queue, result_queue: Queue, progress_queue: Queue,
         stop_event: Event, config_manager: ConfigManager):
    """初始化路由模块引用"""
    global _task_queue, _result_queue, _progress_queue, _stop_event, _config_manager
    _task_queue = task_queue
    _result_queue = result_queue
    _progress_queue = progress_queue
    _stop_event = stop_event
    _config_manager = config_manager


def _drain_queue(q: Queue):
    """清空队列"""
    while not q.empty():
        try:
            q.get_nowait()
        except Empty:
            break


def _poll_progress(q: Queue, timeout: float):
    """在线程中阻塞读取 progress_queue"""
    items = []
    try:
        items.append(q.get(timeout=timeout))
        while True:
            items.append(q.get_nowait())
    except Empty:
        pass
    return items


async def _run_batch(items: list, options: dict, loop: asyncio.AbstractEventLoop):
    """批量执行核心逻辑（在 async task 中运行）"""
    global _batch_running, _batch_results

    model_size = _config_manager.get("MODEL_SIZE", "large-v2")
    lang_code = _config_manager.get("LANGUAGE", "ja")
    prompt = _config_manager.get("PROMPT", "")
    offset_ms = _config_manager.get("OFFSET", 0)
    release_vram = _config_manager.get("RELEASE_VRAM", True)

    total = len(items)
    _batch_results = []

    for idx, item in enumerate(items):
        if _stop_event.is_set():
            _batch_results.append({
                "name": item.get("name", f"item_{idx}"),
                "status": "aborted",
                "result": None,
                "error": "用户中止"
            })
            continue

        item_name = item.get("name", f"item_{idx}")

        # 广播当前项开始
        await batch_ws_manager.broadcast({
            "type": "item_start",
            "item_index": idx,
            "total": total,
            "item_name": item_name,
        })

        try:
            # 获取文件路径
            audio_path = get_uploaded_filepath(item["audio_file_id"])

            # 解析歌词
            parser = LrcParser()
            lyrics_text = item.get("lyrics_text", "")
            raw_content = item.get("raw_content", "")
            current_timestamps = []
            used_raw = False

            if raw_content:
                temp_parser = LrcParser()
                temp_clean = temp_parser.parse(raw_content, ".lrc")

                def normalize(s):
                    return "".join(s.split())

                if normalize(temp_clean) == normalize(lyrics_text):
                    current_timestamps = temp_parser.lines_timestamps
                    parser = temp_parser
                    used_raw = True

            if not used_raw:
                parser.parse(lyrics_text, ".lrc")
                current_timestamps = parser.lines_timestamps

            lrc_parser_data = {
                "headers": parser.headers,
                "lines_text": parser.lines_text,
                "translations": parser.translations,
            }

            # 清空旧消息
            _drain_queue(_result_queue)
            _drain_queue(_progress_queue)
            _stop_event.clear()

            args = WorkerArgs(
                audio_path=audio_path,
                model_size=model_size,
                language=lang_code,
                ref_text=lyrics_text,
                lrc_parser_data=lrc_parser_data,
                time_offset=offset_ms / 1000.0,
                initial_prompt_input=prompt,
                model_dir=_config_manager.get("MODEL_DIR"),
                release_vram=release_vram,
                lrc_timestamps=current_timestamps,
                enable_force_calibration=options.get("enable_force_calibration", True),
                enable_avg_distribution=options.get("enable_avg_distribution", False),
                enable_msst=options.get("enable_msst", False),
                msst_model_key=options.get("msst_model_key", ""),
                msst_model_dir=_config_manager.get("MSST_MODEL_DIR"),
            )

            _task_queue.put(args)

            # 等待结果
            while True:
                if _stop_event.is_set():
                    break

                # 读取进度
                try:
                    progress_msgs = await loop.run_in_executor(
                        None, _poll_progress, _progress_queue, 0.3
                    )
                    for msg in progress_msgs:
                        if isinstance(msg, str):
                            if msg.startswith("PROGRESS:"):
                                try:
                                    val = int(msg.split(":")[1])
                                    await batch_ws_manager.broadcast({
                                        "type": "item_progress",
                                        "item_index": idx,
                                        "total": total,
                                        "item_name": item_name,
                                        "progress": val,
                                    })
                                except (ValueError, IndexError):
                                    pass
                            else:
                                await batch_ws_manager.broadcast({
                                    "type": "item_status",
                                    "item_index": idx,
                                    "total": total,
                                    "item_name": item_name,
                                    "message": msg,
                                })
                except Exception:
                    pass

                # 检查结果
                try:
                    result_type, result_data = _result_queue.get_nowait()
                    if result_type == "success":
                        _batch_results.append({
                            "name": item_name,
                            "status": "success",
                            "result": result_data,
                            "error": None,
                        })
                        await batch_ws_manager.broadcast({
                            "type": "item_complete",
                            "item_index": idx,
                            "total": total,
                            "item_name": item_name,
                            "status": "success",
                        })
                    elif result_type == "error":
                        _batch_results.append({
                            "name": item_name,
                            "status": "error",
                            "result": None,
                            "error": result_data,
                        })
                        await batch_ws_manager.broadcast({
                            "type": "item_complete",
                            "item_index": idx,
                            "total": total,
                            "item_name": item_name,
                            "status": "error",
                            "error": result_data,
                        })
                    elif result_type == "aborted":
                        _batch_results.append({
                            "name": item_name,
                            "status": "aborted",
                            "result": None,
                            "error": "用户中止",
                        })
                    break  # 当前项完成，进入下一项
                except Empty:
                    pass

        except Exception as e:
            _batch_results.append({
                "name": item_name,
                "status": "error",
                "result": None,
                "error": str(e),
            })
            await batch_ws_manager.broadcast({
                "type": "item_complete",
                "item_index": idx,
                "total": total,
                "item_name": item_name,
                "status": "error",
                "error": str(e),
            })

    # 批量完成
    async with _batch_lock:
        _batch_running = False

    success_count = sum(1 for r in _batch_results if r["status"] == "success")
    await batch_ws_manager.broadcast({
        "type": "batch_complete",
        "total": total,
        "success_count": success_count,
        "results": [{"name": r["name"], "status": r["status"], "error": r.get("error")} for r in _batch_results],
    })


@router.post("/start", response_model=BatchStartResponse)
async def start_batch(req: BatchStartRequest):
    """启动批量生成任务"""
    global _batch_running, _batch_task

    async with _batch_lock:
        if _batch_running:
            raise HTTPException(status_code=409, detail="批量任务正在运行中")
        _batch_running = True

    _stop_event.clear()

    # 构建任务列表
    items = []
    for pair in req.items:
        items.append({
            "audio_file_id": pair.audio_file_id,
            "lyrics_text": pair.lyrics_text,
            "raw_content": pair.raw_content,
            "name": pair.name,
        })

    options = {
        "enable_force_calibration": req.enable_force_calibration,
        "enable_avg_distribution": req.enable_avg_distribution,
        "enable_msst": req.enable_msst,
        "msst_model_key": req.msst_model_key,
    }

    loop = asyncio.get_event_loop()
    _batch_task = asyncio.create_task(_run_batch(items, options, loop))

    return BatchStartResponse(
        status="started",
        message=f"批量任务已启动，共 {len(items)} 项"
    )


@router.post("/stop")
async def stop_batch():
    """停止批量任务"""
    global _batch_running
    async with _batch_lock:
        if _stop_event:
            _stop_event.set()
        _batch_running = False
    return {"status": "stopping", "message": "正在停止批量任务..."}


@router.get("/results")
async def get_batch_results():
    """获取批量处理结果列表"""
    return {
        "results": [
            {
                "name": r["name"],
                "status": r["status"],
                "has_result": r["result"] is not None,
                "error": r.get("error"),
            }
            for r in _batch_results
        ]
    }


@router.get("/download/{index}")
async def download_single_result(index: int):
    """下载单个结果"""
    if index < 0 or index >= len(_batch_results):
        raise HTTPException(status_code=404, detail="结果不存在")

    item = _batch_results[index]
    if not item["result"]:
        raise HTTPException(status_code=400, detail="该项无结果")

    from fastapi.responses import Response
    encoded = item["result"].encode("utf-8")
    filename = f"{item['name']}.lrc"

    return Response(
        content=encoded,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-all")
async def download_all_results():
    """打包下载所有成功的结果为 ZIP"""
    from fastapi.responses import StreamingResponse

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in _batch_results:
            if r["result"]:
                filename = f"{r['name']}.lrc"
                zf.writestr(filename, r["result"])

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="batch_results.zip"'},
    )


@router.websocket("/ws")
async def batch_websocket(websocket: WebSocket):
    """批量任务进度 WebSocket"""
    await batch_ws_manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        batch_ws_manager.disconnect(websocket)
    except Exception:
        batch_ws_manager.disconnect(websocket)
