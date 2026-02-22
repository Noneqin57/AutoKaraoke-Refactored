# -*- coding: utf-8 -*-
"""
生成任务 API 路由 + WebSocket 进度桥接

关键设计：
- daemon_worker 的 multiprocessing.Queue/Event 接口完全保持不变
- API 层通过 asyncio + run_in_executor 高效桥接 Queue 到 WebSocket
"""
import asyncio
from queue import Empty
from multiprocessing import Queue, Event
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from core.lrc_parser import LrcParser
from core.whisper_worker import WorkerArgs
from config import ConfigManager
from api.schemas import TaskStartRequest, TaskStartResponse
from api.ws_manager import task_ws_manager
from api.routes_file import get_uploaded_filepath

router = APIRouter(prefix="/task", tags=["task"])

# 由 server.py 注入
_task_queue: Queue = None
_result_queue: Queue = None
_progress_queue: Queue = None
_stop_event: Event = None
_config_manager: ConfigManager = None
_is_running: bool = False
_running_lock = asyncio.Lock()


def init(task_queue: Queue, result_queue: Queue, progress_queue: Queue,
         stop_event: Event, config_manager: ConfigManager):
    """初始化路由模块引用（由 server.py 调用）"""
    global _task_queue, _result_queue, _progress_queue, _stop_event, _config_manager
    _task_queue = task_queue
    _result_queue = result_queue
    _progress_queue = progress_queue
    _stop_event = stop_event
    _config_manager = config_manager


@router.post("/start", response_model=TaskStartResponse)
async def start_task(req: TaskStartRequest):
    """启动生成任务"""
    global _is_running

    async with _running_lock:
        if _is_running:
            raise HTTPException(status_code=409, detail="任务正在运行中")
        _is_running = True

    # 获取音频文件路径
    audio_path = get_uploaded_filepath(req.audio_file_id)

    # 从配置中读取参数
    model_size = _config_manager.get("MODEL_SIZE", "large-v2")
    lang_code = _config_manager.get("LANGUAGE", "ja")
    prompt = _config_manager.get("PROMPT", "")
    offset_ms = _config_manager.get("OFFSET", 0)
    release_vram = _config_manager.get("RELEASE_VRAM", True)

    txt = req.lyrics_text

    # 解析歌词
    current_timestamps = []
    parser = LrcParser()
    used_raw_content = False

    if req.raw_lrc_content:
        temp_parser = LrcParser()
        temp_clean = temp_parser.parse(req.raw_lrc_content, ".lrc")

        def normalize(s):
            return "".join(s.split())

        if normalize(temp_clean) == normalize(txt):
            current_timestamps = temp_parser.lines_timestamps
            parser = temp_parser
            used_raw_content = True

    if not used_raw_content:
        parser.parse(txt, ".lrc")
        current_timestamps = parser.lines_timestamps

    lrc_parser_data = {
        "headers": parser.headers,
        "lines_text": parser.lines_text,
        "translations": parser.translations
    }

    # 重置
    _stop_event.clear()

    # 清空旧消息
    while not _result_queue.empty():
        try:
            _result_queue.get_nowait()
        except Empty:
            pass
    while not _progress_queue.empty():
        try:
            _progress_queue.get_nowait()
        except Empty:
            pass

    args = WorkerArgs(
        audio_path=audio_path,
        model_size=model_size,
        language=lang_code,
        ref_text=txt,
        lrc_parser_data=lrc_parser_data,
        time_offset=offset_ms / 1000.0,
        initial_prompt_input=prompt,
        model_dir=_config_manager.get("MODEL_DIR"),
        release_vram=release_vram,
        lrc_timestamps=current_timestamps,
        enable_force_calibration=req.enable_force_calibration,
        enable_avg_distribution=req.enable_avg_distribution,
        enable_msst=req.enable_msst,
        msst_model_key=req.msst_model_key,
        msst_model_dir=_config_manager.get("MSST_MODEL_DIR"),
    )

    _task_queue.put(args)

    msg = "任务已启动"
    if used_raw_content:
        msg += "（检测到原始时间轴）"

    return TaskStartResponse(status="started", message=msg)


@router.post("/stop")
async def stop_task():
    """停止当前任务"""
    global _is_running
    async with _running_lock:
        if _stop_event:
            _stop_event.set()
        _is_running = False
    return {"status": "stopping", "message": "正在请求停止..."}


def _poll_progress_batch(q: Queue, timeout: float):
    """在线程池中阻塞等待第一条消息，然后批量取出后续消息"""
    items = []
    try:
        # 阻塞等待第一条消息，让出 CPU
        items.append(q.get(timeout=timeout))
        # 非阻塞取出所有后续消息
        while True:
            items.append(q.get_nowait())
    except Empty:
        pass
    return items


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    """
    任务进度 WebSocket。

    使用 run_in_executor 在线程池中阻塞等待 Queue，
    避免 100ms 忙轮询造成 CPU 浪费。

    消息格式：
    - {type: "progress", progress: 50}
    - {type: "status", message: "识别中..."}
    - {type: "result", result: "LRC内容"}
    - {type: "error", message: "错误信息"}
    - {type: "aborted"}
    """
    global _is_running
    await task_ws_manager.connect(websocket)

    loop = asyncio.get_event_loop()

    try:
        while True:
            # 用 run_in_executor 阻塞式等待 progress_queue (timeout=0.2s)
            # 相比 100ms 忙轮询，这种方式在空闲时几乎不消耗 CPU
            try:
                progress_msgs = await loop.run_in_executor(
                    None, _poll_progress_batch, _progress_queue, 0.2
                )
                for msg in progress_msgs:
                    if isinstance(msg, str):
                        if msg.startswith("PROGRESS:"):
                            try:
                                val = int(msg.split(":")[1])
                                await task_ws_manager.send_json(websocket, {
                                    "type": "progress", "progress": val
                                })
                            except (ValueError, IndexError):
                                pass
                        else:
                            await task_ws_manager.send_json(websocket, {
                                "type": "status", "message": msg
                            })
            except Exception:
                pass

            # 非阻塞检查 result_queue
            try:
                result_type, result_data = _result_queue.get_nowait()
                if result_type == "success":
                    await task_ws_manager.send_json(websocket, {
                        "type": "result", "result": result_data
                    })
                elif result_type == "error":
                    await task_ws_manager.send_json(websocket, {
                        "type": "error", "message": result_data
                    })
                elif result_type == "aborted":
                    await task_ws_manager.send_json(websocket, {
                        "type": "aborted"
                    })
                # 任务完成后统一重置 _is_running
                async with _running_lock:
                    _is_running = False
            except Empty:
                pass

            # 检查客户端心跳（非阻塞）
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        task_ws_manager.disconnect(websocket)
    except Exception:
        task_ws_manager.disconnect(websocket)
