# -*- coding: utf-8 -*-
"""音频流 API 路由（支持 HTTP Range 请求）"""
import os
import mimetypes
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from api.routes_file import get_uploaded_filepath

router = APIRouter(prefix="/audio", tags=["audio"])

# MIME 类型映射
MIME_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
}


@router.get("/{file_id}")
async def stream_audio(file_id: str, request: Request):
    """
    音频流端点，支持 HTTP 206 Range 分段请求。
    这允许前端 <audio> 元素的进度条拖动功能。
    """
    filepath = get_uploaded_filepath(file_id)
    file_size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    content_type = MIME_MAP.get(ext, "application/octet-stream")

    # 解析 Range 头
    range_header = request.headers.get("range")

    if range_header:
        # 解析 "bytes=start-end"
        try:
            range_spec = range_header.replace("bytes=", "")
            parts = range_spec.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="无效的 Range 头")

        # 裁剪 end 到合法范围
        if end >= file_size:
            end = file_size - 1

        if start >= file_size or start > end:
            raise HTTPException(status_code=416, detail="Range 超出文件大小")

        content_length = end - start + 1

        def iter_file():
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 64 * 1024  # 64KB 块
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            }
        )
    else:
        # 完整文件响应
        def iter_full():
            with open(filepath, "rb") as f:
                chunk_size = 64 * 1024
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    yield data

        return StreamingResponse(
            iter_full(),
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            }
        )
