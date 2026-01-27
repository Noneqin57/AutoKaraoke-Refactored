# -*- coding: utf-8 -*-
import os
import shutil
import requests
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

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
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            
    def get_model_list(self) -> List[ModelInfo]:
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

    def delete_model(self, model_info: ModelInfo):
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

    def set_mirror(self, mirror_url: Optional[str]):
        if mirror_url:
            self.mirror_url = mirror_url
            # Set environment variable for HF
            os.environ["HF_ENDPOINT"] = mirror_url

    def start(self):
        try:
            if self.model.type == ModelType.FASTER_WHISPER:
                self._download_hf()
            else:
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

    def _download_hf(self):
        # Using huggingface_hub api to list files and download them one by one for progress
        if not HAS_HF_HUB:
            raise ImportError("huggingface_hub not installed")
            
        api = HfApi(endpoint=os.environ.get("HF_ENDPOINT"))
        repo_id = self.model.repo_id_or_url
        target_dir = self.model.local_path
        
        os.makedirs(target_dir, exist_ok=True)
        
        if self.callback: self.callback(0, "Fetching file list...")
        
        # Get list of files
        repo_files = api.list_repo_files(repo_id=repo_id)
        # Filter out git/meta files
        files_to_download = [f for f in repo_files if not f.startswith('.')]
        
        total_files = len(files_to_download)
        
        # Note: Proper size based progress is hard with snapshot_download without a custom tracker
        # and listing all file sizes first is slow. We will use file count + per-file progress if possible
        # Or just download file by file.
        
        for i, filename in enumerate(files_to_download):
            if self.stop_flag: break
            
            if self.callback: 
                self.callback(int((i / total_files) * 100), f"Downloading {filename}...")
            
            # Use requests to download for granular progress within file
            # Get download URL
            # Note: hf_hub_url gives us the url
            # But wait, faster-whisper expects a specific directory structure.
            # Using hf_hub_download is safer but lacks progress callback that is easy to hook.
            # Let's try hf_hub_download with local_dir
            
            try:
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=target_dir
                )
            except TypeError:
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=target_dir,
                    local_dir_use_symlinks=False
                )
            
        if not self.stop_flag and self.callback:
            self.callback(100, "Download Complete")

    def _download_url(self):
        url = self.model.repo_id_or_url
        dest = self.model.local_path
        
        # Ensure dir
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        
        if self.callback: self.callback(0, "Connecting...")
        
        response = requests.get(url, stream=True, timeout=10)
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
            except: pass
        else:
            if self.callback: self.callback(100, "Download Complete")
