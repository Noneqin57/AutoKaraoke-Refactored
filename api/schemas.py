# -*- coding: utf-8 -*-
"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ============ 文件相关 ============

class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    filename: str
    size: int = 0


class LyricsParseResponse(BaseModel):
    """歌词解析响应"""
    clean_text: str
    headers: List[str] = []
    lines_text: List[str] = []
    translations: Dict[str, List[str]] = {}
    timestamps: List[float] = []
    raw_content: str = ""


class LrcDownloadRequest(BaseModel):
    """LRC 文件下载请求"""
    content: str
    encoding: str = "utf-8"
    filename: str = "output.lrc"


# ============ 任务相关 ============

class TaskStartRequest(BaseModel):
    """任务启动请求"""
    audio_file_id: str
    lyrics_text: str = ""
    raw_lrc_content: str = ""
    enable_force_calibration: bool = True
    enable_avg_distribution: bool = False
    enable_msst: bool = False
    msst_model_key: str = ""


class TaskStartResponse(BaseModel):
    """任务启动响应"""
    status: str
    message: str


# ============ 配置相关 ============

class ConfigResponse(BaseModel):
    """配置响应"""
    config: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    updates: Dict[str, Any]


class LanguageItem(BaseModel):
    """语言列表项"""
    code: str
    name: str


class LanguagesResponse(BaseModel):
    """语言列表响应"""
    languages: List[LanguageItem]


# ============ 模型相关 ============

class ModelItem(BaseModel):
    """模型信息"""
    name: str
    type: str
    key: str
    repo_id_or_url: str = ""
    local_path: str = ""
    size_mb: float = 0
    is_downloaded: bool = False


class ModelListResponse(BaseModel):
    """模型列表响应"""
    models: List[ModelItem]


class ModelDownloadRequest(BaseModel):
    """模型下载请求"""
    key: str
    type: str


class ModelDeleteRequest(BaseModel):
    """模型删除请求"""
    key: str
    type: str


# ============ MSST 人声分离模型相关 ============

class MsstModelItem(BaseModel):
    """MSST 人声分离模型信息"""
    key: str
    name: str
    model_type: str
    size_mb: float = 0
    is_downloaded: bool = False


class MsstModelListResponse(BaseModel):
    """MSST 模型列表响应"""
    models: List[MsstModelItem]


class MsstModelDownloadRequest(BaseModel):
    """MSST 模型下载请求"""
    key: str


# ============ 批量处理相关 ============

class BatchItem(BaseModel):
    """批量处理中的单个项"""
    audio_file_id: str
    lyrics_text: str = ""
    raw_content: str = ""
    name: str = ""


class BatchStartRequest(BaseModel):
    """批量任务启动请求"""
    items: List[BatchItem]
    enable_force_calibration: bool = True
    enable_avg_distribution: bool = False
    enable_msst: bool = False
    msst_model_key: str = ""


class BatchStartResponse(BaseModel):
    """批量任务启动响应"""
    status: str
    message: str
