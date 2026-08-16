# -*- coding: utf-8 -*-
"""core.model_manager 完整性校验单元测试（monkeypatch 文件系统，不落盘）。"""
import os

import core.model_manager as mm
from core.model_manager import DownloadStopped, ModelDownloader, ModelInfo, ModelManager, ModelType


class TestOriginalWhisperIntegrity:
    def test_downloaded_when_file_complete(self, monkeypatch):
        monkeypatch.setattr(os.path, "isdir", lambda p: False)
        monkeypatch.setattr(os.path, "isfile", lambda p: True)
        monkeypatch.setattr(os.path, "getsize", lambda p: 2 * 1024 * 1024)
        monkeypatch.setattr(
            os.path,
            "exists",
            lambda p: str(p) == "." or not str(p).endswith(".part"),
        )

        models = ModelManager(".").get_model_list()
        original = [m for m in models if m.type == ModelType.ORIGINAL_WHISPER]
        assert original
        assert all(m.is_downloaded for m in original)

    def test_not_downloaded_when_part_file_exists(self, monkeypatch):
        monkeypatch.setattr(os.path, "isdir", lambda p: False)
        monkeypatch.setattr(os.path, "isfile", lambda p: True)
        monkeypatch.setattr(os.path, "getsize", lambda p: 2 * 1024 * 1024)
        monkeypatch.setattr(
            os.path,
            "exists",
            lambda p: str(p) == "." or str(p).endswith(".part"),
        )

        models = ModelManager(".").get_model_list()
        original = [m for m in models if m.type == ModelType.ORIGINAL_WHISPER]
        assert all(not m.is_downloaded for m in original)

class FakeStreamResponse:
    def __init__(self, chunks, total):
        self.status_code = 200
        self.headers = {"content-length": str(total)}
        self._chunks = chunks

    def iter_content(self, chunk_size):
        yield from self._chunks


class FakeFile:
    def __init__(self):
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, data):
        self.writes.append(data)


def test_url_download_resumes_with_range_header(monkeypatch):
    progress = []
    replace_calls = []
    request_headers = {}
    fake_file = FakeFile()

    monkeypatch.setattr(mm.os.path, "join", lambda *a: "/".join(a))
    monkeypatch.setattr(mm.os.path, "dirname", lambda p: p.rsplit("/", 1)[0] if "/" in p else ".")
    monkeypatch.setattr(mm.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(mm.os.path, "exists", lambda p: True)
    monkeypatch.setattr(mm.os.path, "getsize", lambda p: 2048)
    monkeypatch.setattr(mm.os, "remove", lambda p: None)
    monkeypatch.setattr(mm.os, "replace", lambda a, b: replace_calls.append((a, b)))
    monkeypatch.setattr("builtins.open", lambda *a, **k: fake_file)

    def fake_get(url, stream, timeout, headers=None):
        request_headers.update(headers or {})
        return FakeStreamResponse([b"c" * 2048], 2048)

    monkeypatch.setattr(mm.requests, "get", fake_get)

    model = ModelInfo(
        name="tiny",
        type=ModelType.ORIGINAL_WHISPER,
        key="tiny",
        repo_id_or_url="http://fake/tiny.pt",
        local_path="fake-models/tiny.pt",
    )
    downloader = ModelDownloader(model, lambda pct, msg: progress.append((pct, msg)))

    downloader._download_url_once()

    assert request_headers == {"Range": "bytes=2048-"}
    assert b"".join(fake_file.writes) == b"c" * 2048
    assert (100, "Downloading... 100%") in progress
    assert replace_calls == [("fake-models/tiny.pt.part", "fake-models/tiny.pt")]

def test_stream_download_rejects_416_status(monkeypatch):
    replace_calls = []
    fake_file = FakeFile()

    monkeypatch.setattr(mm.os.path, "exists", lambda p: False)
    monkeypatch.setattr(mm.os.path, "getsize", lambda p: 0)
    monkeypatch.setattr(mm.os, "remove", lambda p: None)
    monkeypatch.setattr(mm.os, "replace", lambda a, b: replace_calls.append((a, b)))
    monkeypatch.setattr("builtins.open", lambda *a, **k: fake_file)

    class Fake416:
        status_code = 416
        headers = {"content-length": "0"}

        def iter_content(self, chunk_size):
            return iter([])

    monkeypatch.setattr(
        mm.requests,
        "get",
        lambda url, stream, timeout, headers=None: Fake416(),
    )

    model = ModelInfo(
        name="tiny",
        type=ModelType.ORIGINAL_WHISPER,
        key="tiny",
        repo_id_or_url="http://fake/tiny.pt",
        local_path="fake-models/tiny.pt",
    )
    downloader = ModelDownloader(model, None)

    try:
        downloader._stream_download(
            "http://fake/tiny.pt", "fake-models/tiny.pt", "fake-models/tiny.pt.part"
        )
    except RuntimeError as exc:
        assert "416" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for HTTP 416")

    assert not replace_calls


def test_stream_download_stop_midway_cleans_part(monkeypatch):
    remove_calls = []
    replace_calls = []
    fake_file = FakeFile()

    monkeypatch.setattr(mm.os.path, "join", lambda *a: "/".join(a))
    monkeypatch.setattr(mm.os.path, "dirname", lambda p: p.rsplit("/", 1)[0] if "/" in p else ".")
    monkeypatch.setattr(mm.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(mm.os.path, "exists", lambda p: False)
    monkeypatch.setattr(mm.os.path, "getsize", lambda p: 0)
    monkeypatch.setattr(mm.os, "remove", lambda p: remove_calls.append(p))
    monkeypatch.setattr(mm.os, "replace", lambda a, b: replace_calls.append((a, b)))
    monkeypatch.setattr("builtins.open", lambda *a, **k: fake_file)

    model = ModelInfo(
        name="tiny",
        type=ModelType.ORIGINAL_WHISPER,
        key="tiny",
        repo_id_or_url="http://fake/tiny.pt",
        local_path="fake-models/tiny.pt",
    )
    downloader = ModelDownloader(model, None)

    class StopResponse:
        status_code = 200
        headers = {"content-length": "2048"}

        def iter_content(self, chunk_size):
            yield b"a" * 1024
            downloader.stop_flag = True
            yield b"b" * 1024

    monkeypatch.setattr(
        mm.requests,
        "get",
        lambda url, stream, timeout, headers=None: StopResponse(),
    )

    completed = downloader._stream_download(
        "http://fake/tiny.pt", "fake-models/tiny.pt", "fake-models/tiny.pt.part"
    )

    assert completed is False
    assert remove_calls == ["fake-models/tiny.pt.part"]
    assert not replace_calls

def test_download_url_once_raises_download_stopped(monkeypatch):
    fake_file = FakeFile()
    remove_calls = []

    monkeypatch.setattr(mm.os.path, "join", lambda *a: "/".join(a))
    monkeypatch.setattr(mm.os.path, "dirname", lambda p: p.rsplit("/", 1)[0] if "/" in p else ".")
    monkeypatch.setattr(mm.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(mm.os.path, "exists", lambda p: False)
    monkeypatch.setattr(mm.os.path, "getsize", lambda p: 0)
    monkeypatch.setattr(mm.os, "remove", lambda p: remove_calls.append(p))
    monkeypatch.setattr(mm.os, "replace", lambda a, b: None)
    monkeypatch.setattr("builtins.open", lambda *a, **k: fake_file)

    model = ModelInfo(
        name="tiny",
        type=ModelType.ORIGINAL_WHISPER,
        key="tiny",
        repo_id_or_url="http://fake/tiny.pt",
        local_path="fake-models/tiny.pt",
    )
    downloader = ModelDownloader(model, None)

    class StopResponse:
        status_code = 200
        headers = {"content-length": "2048"}

        def iter_content(self, chunk_size):
            yield b"a" * 1024
            downloader.stop_flag = True

    monkeypatch.setattr(
        mm.requests,
        "get",
        lambda url, stream, timeout, headers=None: StopResponse(),
    )

    try:
        downloader._download_url_once()
    except DownloadStopped as exc:
        assert "已暂停" in str(exc)
    else:
        raise AssertionError("Expected DownloadStopped")


def test_stream_download_unknown_size_reports_indeterminate(monkeypatch):
    progress = []
    replace_calls = []
    fake_file = FakeFile()

    monkeypatch.setattr(mm.os.path, "join", lambda *a: "/".join(a))
    monkeypatch.setattr(mm.os.path, "dirname", lambda p: p.rsplit("/", 1)[0] if "/" in p else ".")
    monkeypatch.setattr(mm.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(mm.os.path, "exists", lambda p: False)
    monkeypatch.setattr(mm.os.path, "getsize", lambda p: 0)
    monkeypatch.setattr(mm.os, "remove", lambda p: None)
    monkeypatch.setattr(mm.os, "replace", lambda a, b: replace_calls.append((a, b)))
    monkeypatch.setattr("builtins.open", lambda *a, **k: fake_file)

    class NoLengthResponse:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size):
            yield b"a" * 1024
            yield b"b" * 1024

    monkeypatch.setattr(
        mm.requests,
        "get",
        lambda url, stream, timeout, headers=None: NoLengthResponse(),
    )

    model = ModelInfo(
        name="tiny",
        type=ModelType.ORIGINAL_WHISPER,
        key="tiny",
        repo_id_or_url="http://fake/tiny.pt",
        local_path="fake-models/tiny.pt",
    )
    downloader = ModelDownloader(model, lambda pct, msg: progress.append((pct, msg)))

    downloader._stream_download(
        "http://fake/tiny.pt", "fake-models/tiny.pt", "fake-models/tiny.pt.part"
    )

    assert any(pct == -2 for pct, _msg in progress)
    assert replace_calls