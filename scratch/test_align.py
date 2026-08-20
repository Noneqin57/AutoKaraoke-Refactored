import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import io
from multiprocessing import Event
from core.lrc_parser import LrcParser
from core.lrc_aligner_v2 import LrcAligner

class DummyQueue:
    def put(self, m): pass

p = LrcParser()
raw_text = """嫌弃下雨的天气
可怜垮掉的发型
新买的鞋子沾上泥"""

p.parse(raw_text, ".txt")
print("Parsed lines_text:", p.lines_text)
print("Parsed lines_timestamps:", p.lines_timestamps)

aligner = LrcAligner(p, enable_force_calibration=False)

whisper_res = {
    "segments": [
        {
            "start": 25.5,
            "end": 35.0,
            "text": "嫌 弃 下 雨 的 天 气 可 怜 垮 掉 的 发 型 新 买 的 鞋 子 沾 上 泥",
            "words": [
                {"word": "嫌", "start": 25.5, "end": 25.8},
                {"word": "弃", "start": 25.8, "end": 26.0},
                {"word": "下", "start": 26.0, "end": 26.3},
                {"word": "雨", "start": 26.3, "end": 26.6},
                {"word": "的", "start": 26.6, "end": 26.8},
                {"word": "天", "start": 26.8, "end": 27.1},
                {"word": "气", "start": 27.1, "end": 27.5},
                {"word": "可", "start": 27.5, "end": 27.8},
                {"word": "怜", "start": 27.8, "end": 28.0},
                {"word": "垮", "start": 28.0, "end": 28.3},
                {"word": "掉", "start": 28.3, "end": 28.6},
                {"word": "的", "start": 28.6, "end": 28.8},
                {"word": "发", "start": 28.8, "end": 29.2},
                {"word": "型", "start": 29.2, "end": 29.5},
                {"word": "新", "start": 29.5, "end": 29.8},
                {"word": "买", "start": 29.8, "end": 30.1},
                {"word": "的", "start": 30.1, "end": 30.3},
                {"word": "鞋", "start": 30.3, "end": 30.6},
                {"word": "子", "start": 30.6, "end": 30.9},
                {"word": "沾", "start": 30.9, "end": 31.2},
                {"word": "上", "start": 31.2, "end": 31.5},
                {"word": "泥", "start": 31.5, "end": 31.8},
            ]
        }
    ]
}

out = aligner.run(whisper_res, Event(), DummyQueue())
print("ALIGNER OUTPUT:\n", out)
