# -*- coding: utf-8 -*-
import os
import shutil
import requests
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

from utils.ssl_bypass import ssl_bypass_context

# Try to import huggingface_hub for faster-whisper models
try:
    from huggingface_hub import HfApi, hf_hub_download
    HAS_HF_HUB = True
except ImportError:
    HAS_HF_HUB = False

class ModelType:
    FASTER_WHISPER = "Faster-Whisper"
    ORIGINAL_WHISPER = "Original Whisper"

@dataclass
class ModelInfo:
    name: str
    type: str # ModelType
    key: str  # id for logic (e.g. 'large-v2')
    repo_id_or_url: str
    local_path: str = ""
    size_mb: float = 0
    is_downloaded: bool = False

# Mapping for Faster Whisper (Systran)
FASTER_WHISPER_MODELS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
}

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

class ModelManager:
    """Whisper 模型管理器，负责列举、校验和删除模型"""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            
    def get_model_list(self) -> List[ModelInfo]:
        """获取所有可用模型（含下载状态）的信息列表"""
        models = []
        
        # Faster Whisper Models
        if HAS_HF_HUB:
            for name, repo_id in FASTER_WHISPER_MODELS.items():
                # For Faster Whisper, stable-whisper/faster-whisper downloads to a subdir usually
                # But here we implement strict path management.
                # If we use ModelManager, we download to base_dir/faster-whisper-name/
                local_path = os.path.join(self.base_dir, f"faster-whisper-{name}")
                is_downloaded = self._check_faster_whisper_integrity(local_path)
                
                models.append(ModelInfo(
                    name=name,
                    type=ModelType.FASTER_WHISPER,
                    key=name,
                    repo_id_or_url=repo_id,
                    local_path=local_path,
                    is_downloaded=is_downloaded
                ))
        
        # Original Whisper Models
        for name, url in ORIGINAL_WHISPER_MODELS.items():
            local_path = os.path.join(self.base_dir, f"{name}.pt")
            is_downloaded = os.path.exists(local_path) 
            # Could check file size/hash if we want to be strict
            
            models.append(ModelInfo(
                name=name,
                type=ModelType.ORIGINAL_WHISPER,
                key=name,
                repo_id_or_url=url,
                local_path=local_path,
                is_downloaded=is_downloaded
            ))
            
        return models

    def _check_faster_whisper_integrity(self, path: str) -> bool:
        if not os.path.isdir(path):
            return False
        # Minimal check: config.json and model.bin must exist
        required = ["config.json", "model.bin"]
        for f in required:
            if not os.path.exists(os.path.join(path, f)):
                return False
        return True

    def delete_model(self, model_info: ModelInfo) -> None:
        """删除已下载的模型文件或目录"""
        if not model_info.is_downloaded:
            return
            
        try:
            if os.path.isdir(model_info.local_path):
                shutil.rmtree(model_info.local_path)
            elif os.path.isfile(model_info.local_path):
                os.remove(model_info.local_path)
        except Exception as e:
            print(f"Error deleting model: {e}")

class ModelDownloader:
    """Helper to download models with progress callback"""
    def __init__(self, model_info: ModelInfo, progress_callback: Optional[Callable[[int, str], None]] = None):
        self.model = model_info
        self.callback = progress_callback
        self.stop_flag = False
        self.disable_ssl_verify = False

    def set_mirror(self, mirror_url: Optional[str]) -> None:
        """设置 HuggingFace 镜像地址"""
        if mirror_url:
            self.mirror_url = mirror_url
            # Set environment variable for HF
            os.environ["HF_ENDPOINT"] = mirror_url

    def set_ssl_verify(self, disable: bool) -> None:
        """设置是否跳过 SSL 证书验证"""
        self.disable_ssl_verify = disable

    def start(self) -> None:
        """开始下载模型，根据类型分派到 HF 或 URL 下载"""
        try:
            if self.model.type == ModelType.FASTER_WHISPER:
                self._download_hf()
            else:
                self._download_url()
        except Exception as e:
            if self.callback:
                if self.stop_flag:
                    self.callback(-1, "已暂停")
                else:
                    self.callback(-1, f"Error: {str(e)}")
            raise e

    def stop(self) -> None:
        """停止下载"""
        self.stop_flag = True

    def _download_hf(self) -> None:
        """通过 HuggingFace Hub 逐文件下载 Faster-Whisper 模型"""
        if not HAS_HF_HUB:
            raise ImportError("huggingface_hub not installed")

        with ssl_bypass_context(self.disable_ssl_verify):
            api = HfApi(endpoint=os.environ.get("HF_ENDPOINT"))
            repo_id = self.model.repo_id_or_url
            target_dir = self.model.local_path
            
            # 使用临时缓存目录
            temp_cache_dir = os.path.join(target_dir, ".hf_cache_temp")
            os.makedirs(target_dir, exist_ok=True)
            os.makedirs(temp_cache_dir, exist_ok=True)

            if self.callback: self.callback(0, "Fetching file list...")

            repo_files = api.list_repo_files(repo_id=repo_id)
            files_to_download = [f for f in repo_files if not f.startswith('.')]

            total_files = len(files_to_download)

            for i, filename in enumerate(files_to_download):
                if self.stop_flag: break

                if self.callback:
                    self.callback(int((i / total_files) * 100), f"Downloading {filename}...")

                try:
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        local_dir=target_dir,
                        cache_dir=temp_cache_dir,
                        local_dir_use_symlinks=False
                    )
                except TypeError:
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        local_dir=target_dir,
                        # 某些旧版本可能不支持 cache_dir 或 local_dir_use_symlinks 组合
                        local_dir_use_symlinks=False
                    )

            # 清理临时缓存
            if os.path.exists(temp_cache_dir):
                try:
                    shutil.rmtree(temp_cache_dir)
                except Exception as e:
                    print(f"Failed to clean temp cache: {e}")

            # 清理默认缓存目录 (models/models--Systran--faster-whisper-small)
            try:
                parent_dir = os.path.dirname(target_dir)
                formatted_repo = repo_id.replace("/", "--")
                default_cache_path = os.path.join(parent_dir, f"models--{formatted_repo}")
                
                if os.path.exists(default_cache_path) and os.path.isdir(default_cache_path):
                     shutil.rmtree(default_cache_path)
                     if self.callback: self.callback(99, "Cleaning up cache...")
            except Exception as e:
                print(f"Failed to clean default cache: {e}")

            if not self.stop_flag and self.callback:
                self.callback(100, "Download Complete")

    def _download_url(self) -> None:
        """通过 URL 流式下载 Original Whisper 模型"""
        url = self.model.repo_id_or_url
        dest = self.model.local_path

        # Ensure dir
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if self.callback: self.callback(0, "Connecting...")

        verify_ssl = not self.disable_ssl_verify
        response = requests.get(url, stream=True, timeout=10, verify=verify_ssl)
        total_size = int(response.headers.get('content-length', 0))
        
        if response.status_code != 200:
            raise Exception(f"HTTP Error: {response.status_code}")
            
        downloaded = 0
        chunk_size = 1024 * 1024 # 1MB
        
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if self.stop_flag: 
                    break
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and self.callback:
                        percent = int((downloaded / total_size) * 100)
                        self.callback(percent, f"Downloading... {percent}%")
                        
        if self.stop_flag:
            # Cleanup partial
            try:
                os.remove(dest)
            except OSError:
                pass
        else:
            if self.callback: self.callback(100, "Download Complete")
