# -*- coding: utf-8 -*-
import os
import shutil
import requests
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable

from config import VOCAL_MODEL_REGISTRY

logger = logging.getLogger(__name__)

class ModelType:
    ORIGINAL_WHISPER = "Original Whisper"
    MSST_VOCAL = "MSST Vocal Separation"

class DownloadStopped(Exception):
    """用户主动停止下载。"""

MAX_DOWNLOAD_RETRIES = 5
RETRY_BACKOFF_BASE = 2

@dataclass
class ModelInfo:
    name: str
    type: str # ModelType
    key: str  # id for logic (e.g. 'large-v2')
    repo_id_or_url: str
    local_path: str = ""
    size_mb: float = 0
    is_downloaded: bool = False

# Mapping for Original Whisper (OpenAI)
# URLs from https://github.com/openai/whisper/blob/main/whisper/__init__.py
ORIGINAL_WHISPER_MODELS = {
    "tiny": "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt",
    "base": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
    "small": "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
    "medium": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt",
    "large-v2": "https://openaipublic.azureedge.net/main/whisper/models/81f7c96c852ee8fc832187b0132e569d6c3065a325277c48f98821585cdbf802/large-v2.pt",
    "large-v3": "https://openaipublic.azureedge.net/main/whisper/models/e5b1a55b89c1367dacf97e3e19bfd829a0153013067238c38a0f603f08faf288/large-v3.pt"
}

# Mapping for MSST / RoFormer / UVR Vocal Separation Models
# 派生自 config.VOCAL_MODEL_REGISTRY（单一数据源），此处仅保留下载所需字段
MSST_VOCAL_MODELS = {
    key: {
        "filename": meta["filename"],
        "url": meta["url"],
        "size_mb": meta["size_mb"],
    }
    for key, meta in VOCAL_MODEL_REGISTRY.items()
}

class ModelManager:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            
    def get_model_list(self) -> List[ModelInfo]:
        models = []
        
        # 1. Original Whisper Models
        for name, url in ORIGINAL_WHISPER_MODELS.items():
            local_path = os.path.join(self.base_dir, f"{name}.pt")
            is_downloaded = (
                os.path.isfile(local_path)
                and os.path.getsize(local_path) > 1024 * 1024
                and not os.path.exists(local_path + ".part")
            )
            models.append(ModelInfo(
                name=name,
                type=ModelType.ORIGINAL_WHISPER,
                key=name,
                repo_id_or_url=url,
                local_path=local_path,
                is_downloaded=is_downloaded
            ))
            
        # 2. MSST Vocal Separation Models
        vocal_dir = os.path.join(self.base_dir, "vocal_models")
        for key, meta in MSST_VOCAL_MODELS.items():
            local_path = os.path.join(vocal_dir, meta["filename"])
            is_downloaded = (
                os.path.isfile(local_path)
                and os.path.getsize(local_path) > 1024 * 1024
                and not os.path.exists(local_path + ".part")
            )
            models.append(ModelInfo(
                name=meta["filename"],
                type=ModelType.MSST_VOCAL,
                key=key,
                repo_id_or_url=meta["url"],
                local_path=local_path,
                size_mb=meta.get("size_mb", 0),
                is_downloaded=is_downloaded
            ))

        return models

    def delete_model(self, model_info: ModelInfo):
        if not model_info.is_downloaded:
            return
            
        try:
            if os.path.isdir(model_info.local_path):
                shutil.rmtree(model_info.local_path)
            elif os.path.isfile(model_info.local_path):
                os.remove(model_info.local_path)
        except Exception as e:
            logger.error("Error deleting model: %s", e)

class ModelDownloader:
    """Helper to download models with progress callback"""
    def __init__(self, model_info: ModelInfo, progress_callback: Optional[Callable[[int, str], None]] = None):
        self.model = model_info
        self.callback = progress_callback
        self.stop_flag = False

    def start(self):
        try:
            self._download_url()
        except Exception as e:
            if self.callback:
                # If stopped manually, it might not be an error
                if self.stop_flag:
                    self.callback(-1, "已暂停")
                else:
                    self.callback(-1, f"Error: {str(e)}")
            # Do not re-raise if we handle it via callback, but let the worker know
            raise e

    def stop(self):
        self.stop_flag = True

    def _stream_download(self, url, dest, part_path, start_percent=0, end_percent=100, label="Downloading"):
        """流式下载核心：Range 断点续传 + 字节进度 + .part 原子改名。

        Returns:
            True  —— 下载完成并已原子改名
            False —— 用户停止，.part 已清理
        """
        resume_pos = 0
        if os.path.exists(part_path):
            try:
                resume_pos = os.path.getsize(part_path)
            except OSError:
                resume_pos = 0

        headers = {}
        mode = 'wb'
        if resume_pos > 0:
            headers['Range'] = f"bytes={resume_pos}-"
            mode = 'ab'

        response = requests.get(url, stream=True, timeout=(5, 30), headers=headers)
        if response.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {response.status_code}")
        if response.status_code == 200:
            # 服务器不支持断点：从头下载
            resume_pos = 0
            mode = 'wb'

        total_remaining = int(response.headers.get('content-length', 0))
        received = 0
        with open(part_path, mode) as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if self.stop_flag:
                    break
                if chunk:
                    f.write(chunk)
                    received += len(chunk)
                    if self.callback:
                        if total_remaining > 0:
                            total_expected = resume_pos + total_remaining
                            current = resume_pos + received
                            frac = min(1.0, current / max(1, total_expected))
                            pct = int(
                            start_percent + frac * (end_percent - start_percent)
                            )
                            self.callback(pct, f"{label}... {pct}%")
                        else:
                            received_mb = received / (1024 * 1024)
                            self.callback(-2, f"{label}... 已接收 {received_mb:.1f} MB")


        if self.stop_flag:
            try:
                os.remove(part_path)
            except OSError:
                pass
            return False

        if total_remaining > 0 and received < total_remaining:
            raise RuntimeError(
                f"Incomplete download: {received}/{total_remaining} bytes"
            )

        if total_remaining == 0 and received == 0:
            raise RuntimeError("Empty response body")

        os.replace(part_path, dest)
        return True

    def _download_url_once(self):
        url = self.model.repo_id_or_url
        dest = self.model.local_path
        part_path = dest + ".part"
        
        # Ensure dir
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        
        if self.callback: self.callback(0, "Connecting...")

        completed = self._stream_download(url, dest, part_path, label="Downloading")
        if not completed:
            raise DownloadStopped("已暂停")
        if completed and self.callback:
            self.callback(100, "Download Complete")
        return


    def _download_url(self):
        """带重试的 URL 下载入口，内部调用 _download_url_once。"""
        dest = self.model.local_path

        os.makedirs(os.path.dirname(dest), exist_ok=True)

        last_error = None
        for attempt in range(1, 4):
            if self.stop_flag:
                break
            try:
                self._download_url_once()
                return
            except Exception as e:
                last_error = e
                logger.warning("Model download attempt %d/3 failed: %s", attempt, e)
                if self.callback:
                    self.callback(0, f"Retry {attempt}/3: {e}")
                time.sleep(1)

        if self.stop_flag:
            # 只清理未完成的 .part；保留 dest 处已存在的完整模型，避免误删
            self._remove_part_file(dest)
            raise DownloadStopped("已暂停")

        # 3 次失败后清理残留的 .part 临时文件（同样保留已存在的完整旧模型）
        self._remove_part_file(dest)

        logger.error("Model download failed after 3 attempts: %s", last_error)
        raise last_error if last_error else Exception("Download failed")

    @staticmethod
    def _remove_part_file(dest: str):
        """清理下载残留的 .part 临时文件（不触碰已完成的模型文件）。"""
        try:
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
        except OSError:
            pass