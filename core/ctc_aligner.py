# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
CTC 歌声与歌词强制对齐引擎 (CTC Forced Aligner).
基于 TorchAudio MMS_FA (Meta Multilingual Forced Aligner) 模型与 Viterbi Trellis 动态规划，
专用于歌声长拖音、重颤音与高精度逐字打轴。
"""
import os
import re
import gc
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    import torch
    import torchaudio
except ImportError:
    torch = None
    torchaudio = None

try:
    import pypinyin
except ImportError:
    pypinyin = None

try:
    import pykakasi
    _kakasi_instance = pykakasi.kakasi()
except ImportError:
    pykakasi = None
    _kakasi_instance = None

from core.lrc_parser import LrcParser
from utils.logger_v2 import setup_logger

logger = setup_logger("CTCAligner")


class CTCModelCache:
    """CTC 对齐模型缓存管理器"""
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.aligner = None
        self.dictionary = None
        self.device = None

    def get(self, device: str):
        if self.model is not None and str(self.device) == str(device):
            return self.model, self.tokenizer, self.aligner, self.dictionary
        return None

    def set(self, model, tokenizer, aligner, dictionary, device: str):
        self.model = model
        self.tokenizer = tokenizer
        self.aligner = aligner
        self.dictionary = dictionary
        self.device = device

    def clear(self):
        try:
            if self.model is not None:
                if hasattr(self.model, "to"):
                    self.model.to("cpu")
                del self.model
        except Exception as e:
            logger.debug("Error clearing CTC model: %s", e)
        self.model = None
        self.tokenizer = None
        self.aligner = None
        self.dictionary = None
        self.device = None
        gc.collect()
        if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()


_ctc_model_cache = CTCModelCache()


def split_text_into_phonetic_units(text: str) -> List[Tuple[str, str]]:
    """
    将文本拆解为 (原始字符/词, 罗马音/拼音音素) 的元组列表。
    - 日语文本: 使用 pykakasi 将日文（汉字/假名）转为 Hepburn 罗马音并逐字拆分
    - 中文字符: 逐字拆为拼音（如 '天' -> 'tian'）
    - 英文单词/数字: 保持整词并清洗为小写字母（如 'Hello' -> 'hello'）
    - 标点符号与空白字符自动跳过
    """
    if not text:
        return []

    # 检查是否含有日文假名（平假名/片假名）
    has_japanese = bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text))

    if has_japanese and _kakasi_instance is not None:
        res = _kakasi_instance.convert(text)
        tokens = []
        for item in res:
            orig = item['orig'].strip()
            hep = re.sub(r"[^a-z']", '', item['hepburn'].lower())
            if not orig or not hep:
                continue
            if len(orig) == 1:
                tokens.append((orig, hep))
            elif all('\u3040' <= c <= '\u30ff' for c in orig):
                for c in orig:
                    sub = _kakasi_instance.convert(c)
                    sub_h = re.sub(r"[^a-z']", '', sub[0]['hepburn'].lower()) if sub else 'a'
                    tokens.append((c, sub_h or 'a'))
            else:
                # 多汉字复合词：优先尝试单字符转换，若拼合一致直接采用，否则按字符等比切分
                char_heps = []
                for c in orig:
                    sub = _kakasi_instance.convert(c)
                    sub_h = re.sub(r"[^a-z']", '', sub[0]['hepburn'].lower()) if sub else 'a'
                    char_heps.append(sub_h)
                if ''.join(char_heps) == hep:
                    for c, h in zip(orig, char_heps):
                        tokens.append((c, h))
                else:
                    total_len = len(hep)
                    n = len(orig)
                    step = total_len / n
                    for idx, c in enumerate(orig):
                        start = int(idx * step)
                        end = total_len if idx == n - 1 else int((idx + 1) * step)
                        tokens.append((c, hep[start:end] or 'a'))
        return tokens

    # 中文 / 英文模式
    tokens = []
    pattern = re.finditer(r"([a-zA-Z0-9']+|[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])", text)
    for match in pattern:
        token_str = match.group()
        # 判断是否为汉字
        if len(token_str) == 1 and '\u4e00' <= token_str <= '\u9fa5':
            # 汉字转拼音
            if pypinyin is not None:
                py = pypinyin.lazy_pinyin(token_str)
                py_str = py[0].lower() if py else ""
                py_clean = re.sub(r"[^a-z']", "", py_str)
            else:
                py_clean = "c"  # 占位音素，保证未装 pypinyin 时（如极简 CI 环境）分词结构不丢失
            if py_clean:
                tokens.append((token_str, py_clean))
        elif len(token_str) == 1 and ('\u3040' <= token_str <= '\u309f' or '\u30a0' <= token_str <= '\u30ff'):
            # 日文假名在无 pykakasi 极简环境下的占位保护
            tokens.append((token_str, "a"))
        else:
            # 英文单词或数字（清理为支持的字符）
            clean_str = re.sub(r"[^a-z']", "", token_str.lower())
            if clean_str:
                tokens.append((token_str, clean_str))

    return tokens


def load_audio_waveform(audio_path: str, target_sr: int = 16000) -> Tuple[Any, float]:
    """
    通用音频加载器：优先使用 whisper.audio.load_audio（基于 ffmpeg，原生支持 FLAC/MP3/WAV/M4A/OGG，无需 torchcodec/soundfile），
    若不可用则回退至 torchaudio.load。
    返回: (waveform: torch.Tensor [1, num_samples], duration_sec: float)
    """
    try:
        import whisper
        arr = whisper.audio.load_audio(audio_path, sr=target_sr)
        waveform = torch.from_numpy(arr).unsqueeze(0)
        duration_sec = waveform.size(1) / target_sr
        return waveform, duration_sec
    except Exception as e:
        logger.debug("whisper.audio.load_audio failed: %s. Falling back to torchaudio.load.", e)

    if torch is None or torchaudio is None:
        raise ImportError("需要 PyTorch 与 TorchAudio 支持。")

    waveform, sr = torchaudio.load(audio_path)
    if sr != target_sr:
        waveform = torchaudio.functional.resample(waveform, sr, target_sr)
    waveform = waveform.mean(dim=0, keepdim=True)
    duration_sec = waveform.size(1) / target_sr
    return waveform, duration_sec


class CTCAligner:
    """
    基于 MMS_FA 的 CTC 歌声强制对齐执行器
    """
    def __init__(self, device: Optional[str] = None):
        if torch is None or torchaudio is None:
            raise ImportError("CTCAligner 需要 PyTorch 与 TorchAudio 支持。")

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        self.bundle = torchaudio.pipelines.MMS_FA
        self.sample_rate = self.bundle.sample_rate

    def load_model(self):
        """加载并缓存 MMS_FA 模型"""
        global _ctc_model_cache
        cached = _ctc_model_cache.get(self.device)
        if cached is not None:
            self.model, self.tokenizer, self.aligner, self.dictionary = cached
            return

        logger.info("Loading MMS_FA model on %s...", self.device)
        self.model = self.bundle.get_model().to(self.device)
        self.model.eval()
        self.tokenizer = self.bundle.get_tokenizer()
        self.aligner = self.bundle.get_aligner()
        self.dictionary = self.bundle.get_dict()

        _ctc_model_cache.set(
            self.model, self.tokenizer, self.aligner, self.dictionary, self.device
        )
        logger.info("MMS_FA model loaded and cached successfully.")

    def release(self):
        """释放模型与显存"""
        global _ctc_model_cache
        _ctc_model_cache.clear()

    @torch.inference_mode()
    def align_audio_segment(
        self,
        waveform_slice: Any,
        line_text: str,
        slice_offset_sec: float
    ) -> List[Dict[str, Any]]:
        """
        对单段音频切片进行 CTC 强制对齐
        :param waveform_slice: 形状为 (1, num_samples) 的单声道音频张量 (16000Hz)
        :param line_text: 该段音频对应的单行歌词文本
        :param slice_offset_sec: 该切片在整首歌中的起始秒数
        :return: 包含逐字时间戳的列表 [{'word': '海', 'start': 1.2, 'end': 1.6, 'score': 0.95}, ...]
        """
        units = split_text_into_phonetic_units(line_text)
        if not units:
            return []

        # 拼接目标音素序列
        full_phonetic_text = "".join(u[1] for u in units)
        token_indices = self.tokenizer(full_phonetic_text)
        if not token_indices:
            return []

        # 音频前向计算 emission
        waveform_slice = waveform_slice.to(self.device)
        emission, _ = self.model(waveform_slice)
        
        num_frames = emission.size(1)
        if num_frames == 0:
            return []
            
        slice_duration_sec = waveform_slice.size(1) / self.sample_rate
        time_per_frame = slice_duration_sec / num_frames

        try:
            # MMS_FA aligner 接受 2D emission [num_frames, num_tokens] 与 nested token list
            aligned_nested = self.aligner(emission[0], token_indices)
            # 扁平化为 TokenSpan 列表
            spans = [s for sub in aligned_nested for s in sub]
        except Exception as e:
            logger.warning("CTC Trellis alignment failed for line '%s': %s. Falling back to even distribution.", line_text, e)
            return self._fallback_even_distribution(units, slice_offset_sec, slice_duration_sec)

        # 一致性校验：span 数必须与音素字符数一致（MMS 分词为逐字符），
        # 否则字-时间映射会整体错位并静默丢字，宁可整行走均摊兜底
        expected_tokens = sum(len(u[1]) for u in units)
        if len(spans) != expected_tokens:
            logger.warning(
                "CTC token span count mismatch for line '%s' (expected %d, got %d). "
                "Falling back to even distribution.",
                line_text, expected_tokens, len(spans),
            )
            return self._fallback_even_distribution(units, slice_offset_sec, slice_duration_sec)

        words_result = []
        token_cursor = 0

        for orig_word, phonetic_part in units:
            p_len = len(phonetic_part)
            if token_cursor + p_len <= len(spans):
                word_spans = spans[token_cursor : token_cursor + p_len]
                if len(word_spans) > 0:
                    start_frame = word_spans[0].start
                    end_frame = word_spans[-1].end
                    
                    w_start = round(slice_offset_sec + start_frame * time_per_frame, 3)
                    w_end = round(slice_offset_sec + end_frame * time_per_frame, 3)
                    if w_end <= w_start:
                        w_end = round(w_start + 0.05, 3)

                    # TokenSpan 自带 score (对数后验概率转换后的置信度)
                    prob_scores = [getattr(s, "score", 1.0) for s in word_spans]
                    prob = sum(prob_scores) / len(prob_scores) if prob_scores else 1.0

                    words_result.append({
                        "word": orig_word,
                        "start": w_start,
                        "end": w_end,
                        "probability": round(float(prob), 3)
                    })
            token_cursor += p_len

        return words_result

    def _fallback_even_distribution(
        self,
        units: List[Tuple[str, str]],
        start_sec: float,
        duration_sec: float
    ) -> List[Dict[str, Any]]:
        """均摊兜底策略"""
        if not units or duration_sec <= 0:
            return []
        step = duration_sec / len(units)
        results = []
        for i, (orig_word, _) in enumerate(units):
            w_start = round(start_sec + i * step, 3)
            w_end = round(start_sec + (i + 1) * step, 3)
            results.append({
                "word": orig_word,
                "start": w_start,
                "end": w_end,
                "probability": 0.5
            })
        return results

    def align(
        self,
        audio_path: str,
        parser: LrcParser,
        ref_text: str,
        stop_event: Optional[Any] = None,
        progress_queue: Optional[Any] = None,
        time_offset: float = 0.0
    ) -> Dict[str, Any]:
        """
        对整首音频及歌词执行 CTC 强制对齐，输出兼容 LrcAligner 的结果结构。
        """
        self.load_model()

        if progress_queue:
            progress_queue.put("正在载入并重采样音频 (16kHz)...")
            progress_queue.put("PROGRESS:35")

        waveform, total_audio_sec = load_audio_waveform(audio_path, self.sample_rate)

        lines_text = parser.lines_text if parser and parser.lines_text else []
        timestamps = parser.lines_timestamps if parser and parser.lines_timestamps else []

        if not lines_text and ref_text:
            lines_text = [l.strip() for l in ref_text.splitlines() if l.strip()]

        if not lines_text:
            raise ValueError("CTC 强制对齐需要提供有效的歌词底稿！")

        segments = []
        num_lines = len(lines_text)

        logger.info("Starting CTC alignment for %d lines. Total audio duration: %.2fs", num_lines, total_audio_sec)

        # 检查是否有行级时间戳供切片对齐
        has_line_timestamps = len(timestamps) == num_lines and any(t > 0 for t in timestamps)

        for i, line in enumerate(lines_text):
            if stop_event and stop_event.is_set():
                logger.info("CTC alignment aborted by user.")
                return {"segments": []}

            if progress_queue:
                progress_pct = 40 + int((i / max(1, num_lines)) * 45)
                progress_queue.put(f"PROGRESS:{progress_pct}")
                progress_queue.put(f"CTC 正在对齐第 {i + 1}/{num_lines} 行...")

            if not line.strip():
                continue

            # 确定当前行音频切片区间
            if has_line_timestamps and timestamps[i] >= 0:
                line_start = max(0.0, timestamps[i] + time_offset)
                # 计算结束时间（下一行起点或当前行+10s）
                if i + 1 < num_lines and timestamps[i + 1] > timestamps[i]:
                    line_end = min(total_audio_sec, timestamps[i + 1] + time_offset)
                else:
                    line_end = min(total_audio_sec, line_start + 10.0)
            else:
                # 若无行级时间戳，按整首歌均摊估计窗口
                line_start = max(0.0, (i / num_lines) * total_audio_sec)
                line_end = min(total_audio_sec, ((i + 1) / num_lines) * total_audio_sec)

            # 加入 0.2s 的边界 Padding，防止首尾咬字被切断
            pad_before = 0.2 if line_start >= 0.2 else line_start
            pad_after = 0.2 if line_end + 0.2 <= total_audio_sec else (total_audio_sec - line_end)

            slice_start_sample = int((line_start - pad_before) * self.sample_rate)
            slice_end_sample = int((line_end + pad_after) * self.sample_rate)
            waveform_slice = waveform[:, slice_start_sample:slice_end_sample]

            if waveform_slice.size(1) == 0:
                continue

            actual_offset = line_start - pad_before
            words = self.align_audio_segment(waveform_slice, line, actual_offset)

            if words:
                seg_start = words[0]["start"]
                seg_end = words[-1]["end"]
            else:
                seg_start = line_start
                seg_end = line_end

            segments.append({
                "text": line,
                "start": seg_start,
                "end": seg_end,
                "words": words
            })

        logger.info("CTC alignment completed. Generated %d segments.", len(segments))
        return {"segments": segments}
