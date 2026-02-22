# -*- coding: utf-8 -*-
"""文件上传/下载 API 路由"""
import os
import uuid
import tempfile
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response

from core.lrc_parser import LrcParser
from api.schemas import FileUploadResponse, LyricsParseResponse, LrcDownloadRequest

router = APIRouter(prefix="/file", tags=["file"])

# 上传文件临时存储 {file_id: filepath}
_uploaded_files: dict = {}

# 临时目录
_upload_dir = os.path.join(tempfile.gettempdir(), "reatk_uploads")
os.makedirs(_upload_dir, exist_ok=True)


def cleanup_uploaded_files():
    """清理所有上传的临时文件（应用关闭时调用）"""
    for file_id, path in list(_uploaded_files.items()):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    _uploaded_files.clear()

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac"}
LYRICS_EXTENSIONS = {".lrc", ".txt", ".srt"}


def get_uploaded_filepath(file_id: str) -> str:
    """获取上传文件的路径（供其他模块使用）"""
    path = _uploaded_files.get(file_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")
    return path


@router.post("/upload/audio", response_model=FileUploadResponse)
async def upload_audio(file: UploadFile = File(...)):
    """上传音频文件"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式: {ext}")

    file_id = str(uuid.uuid4())
    # 保持原始扩展名
    save_path = os.path.join(_upload_dir, f"{file_id}{ext}")

    # 分块写入，避免大文件占满内存
    total_size = 0
    async with aiofiles.open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            await f.write(chunk)
            total_size += len(chunk)

    _uploaded_files[file_id] = save_path

    return FileUploadResponse(
        file_id=file_id,
        filename=file.filename,
        size=total_size
    )


@router.post("/upload/lyrics", response_model=LyricsParseResponse)
async def upload_lyrics(file: UploadFile = File(...)):
    """上传歌词文件，解析并返回结构化数据"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in LYRICS_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的歌词格式: {ext}")

    raw_bytes = await file.read()

    # 尝试多种编码
    raw_content = ""
    for enc in ["utf-8", "gbk", "utf-8-sig", "big5"]:
        try:
            raw_content = raw_bytes.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if not raw_content:
        raise HTTPException(status_code=400, detail="无法解码歌词文件，请检查文件编码")

    parser = LrcParser()
    clean_text = parser.parse(raw_content, ext)

    # translations 转换 key 为 str（JSON 要求 key 为 string）
    translations_str = {str(k): v for k, v in parser.translations.items()}

    return LyricsParseResponse(
        clean_text=clean_text,
        headers=parser.headers,
        lines_text=parser.lines_text,
        translations=translations_str,
        timestamps=parser.lines_timestamps,
        raw_content=raw_content
    )


@router.post("/download/lrc")
async def download_lrc(req: LrcDownloadRequest):
    """生成 LRC 文件下载"""
    try:
        encoded = req.content.encode(req.encoding)
    except (UnicodeEncodeError, LookupError) as e:
        raise HTTPException(status_code=400, detail=f"编码错误: {e}")

    return Response(
        content=encoded,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{req.filename}"'
        }
    )
