# -*- coding: utf-8 -*-
"""config.ConfigManager 默认值与原子保存测试（不落盘）。"""
import io
import json
import threading

import config as config_mod


def test_default_config_applied_when_file_missing(monkeypatch):
    monkeypatch.setattr(config_mod.os.path, "exists", lambda p: False)
    manager = config_mod.ConfigManager("settings-test.json")

    assert manager.get("MODEL_DIR") == "./models"
    assert manager.get("OUTPUT_DIR") == ""
    assert manager.get("CALIBRATION_THRESHOLD") == 1.5


class _FakeFile:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, data):
        self._sink.append(data)


def test_save_creates_parent_dir_and_replaces_atomically(monkeypatch):
    manager = config_mod.ConfigManager.__new__(config_mod.ConfigManager)
    manager.config_file = "cfg/settings.json"
    manager.config = {"MODEL_SIZE": "small"}
    manager._lock = threading.Lock()

    calls = {"makedirs": [], "replace": [], "writes": []}
    monkeypatch.setattr(config_mod.os.path, "dirname", lambda p: "cfg")
    monkeypatch.setattr(
        config_mod.os,
        "makedirs",
        lambda path, exist_ok=False: calls["makedirs"].append((path, exist_ok)),
    )
    monkeypatch.setattr(config_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(config_mod.os, "replace", lambda a, b: calls["replace"].append((a, b)))
    monkeypatch.setattr(config_mod.os, "rename", lambda a, b: None)
    monkeypatch.setattr(config_mod.os, "remove", lambda p: None)
    monkeypatch.setattr("builtins.open", lambda *a, **k: _FakeFile(calls["writes"]))

    manager.save()

    assert calls["makedirs"][0] == ("cfg", True)
    assert calls["replace"] == [("cfg/settings.json.tmp", "cfg/settings.json")]
    assert json.loads("".join(calls["writes"])) == {"MODEL_SIZE": "small"}


def test_load_existing_config(monkeypatch):
    monkeypatch.setattr(config_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **k: io.StringIO(
            '{"MODEL_SIZE": "small"}'
        ),
    )

    manager = config_mod.ConfigManager("settings.json")

    assert manager.get("MODEL_SIZE") == "small"


def test_corrupt_config_falls_back_to_defaults(monkeypatch):
    monkeypatch.setattr(config_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.StringIO("{bad json"))

    manager = config_mod.ConfigManager("settings.json")

    assert manager.get("MODEL_DIR") == "./models"