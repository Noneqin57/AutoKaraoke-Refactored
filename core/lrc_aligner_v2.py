# -*- coding: utf-8 -*-
"""LRC 逐字对齐核心（清理版）。

只保留当前生效的全局 token 对齐实现，移除历史贪心窗口搜索
（_map_lines_to_segments / _match_time_for_line）与旧字符级实现。
"""
import re
from functools import lru_cache
from multiprocessing import Event, Queue
from typing import Any, Dict, List

import difflib

from config import MIN_DURATION
from core.lrc_parser import LrcParser
from utils.logger_v2 import setup_logger
from utils.time_utils import format_time

logger = setup_logger("Worker")


class LrcAligner:
    def __init__(
        self,
        parser: LrcParser,
        time_offset: float = 0.0,
        enable_force_calibration: bool = True,
        enable_avg_distribution: bool = False,
        calibration_threshold: float = 1.5,
    ):
        self.parser = parser
        self.time_offset = time_offset
        self.enable_force_calibration = enable_force_calibration
        self.enable_avg_distribution = enable_avg_distribution
        self.calibration_threshold = calibration_threshold
        self.ai_words_pool: List[Dict[str, Any]] = []

    def run(self, whisper_result: Any, stop_event: Event, progress_queue: Queue) -> str:
        """执行对齐主逻辑（全局序列对齐版）。"""
        logger.info("=== Starting LrcAligner Run ===")
        logger.info(f"Input lines count: {len(self.parser.lines_text)}")
        if self.parser.lines_timestamps:
            valid_ts_count = sum(1 for t in self.parser.lines_timestamps if t > 0)
            logger.info(
                f"Input lines with valid timestamps: "
                f"{valid_ts_count}/{len(self.parser.lines_timestamps)}"
            )

        output_lines = []
        for header in self.parser.headers:
            output_lines.append(header)
        if self.parser.headers:
            output_lines.append("")

        # 1. 提取所有 AI 识别出的单词
        self._extract_words_from_result(whisper_result)
        logger.info(f"Extracted {len(self.ai_words_pool)} words from Whisper result.")

        # 2. 没有参考文本时直接输出识别结果
        if not self.parser.lines_text:
            logger.info("No reference text provided. Generating raw LRC.")
            return self._generate_raw_lrc(whisper_result, stop_event)

        progress_queue.put("正在执行全局序列对齐...")

        # 3/4. 准备用户与 AI 的全局 token 序列
        user_char_sequence = self._prepare_user_sequence()
        ai_char_sequence = self._prepare_ai_sequence_tokens()
        logger.info(f"User char sequence length: {len(user_char_sequence)}")
        logger.info(f"AI char sequence length: {len(ai_char_sequence)}")

        # 5. 全局序列比对
        user_tokens_str = [t.get('clean_text', '') for t in user_char_sequence]
        ai_tokens_str = [t['text'] for t in ai_char_sequence]
        matcher = difflib.SequenceMatcher(None, user_tokens_str, ai_tokens_str)
        logger.info(f"Sequence matching ratio: {matcher.ratio():.4f}")

        # 6. 回填时间戳
        last_valid_time = 0.0
        match_stats = {'equal': 0, 'replace': 0, 'delete': 0, 'insert': 0}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            match_stats[tag] += i2 - i1
            if tag == 'equal':
                for k in range(i2 - i1):
                    user_idx = i1 + k
                    ai_idx = j1 + k
                    matched_time = ai_char_sequence[ai_idx]['start']
                    if matched_time < last_valid_time:
                        matched_time = last_valid_time
                    user_char_sequence[user_idx]['time'] = matched_time
                    last_valid_time = matched_time
            elif tag == 'replace':
                # 替换区间做一层局部比对，挽救可匹配 token
                last_valid_time = self._match_replace_region(
                    user_char_sequence, ai_char_sequence,
                    i1, i2, j1, j2, last_valid_time,
                )
            elif tag == 'delete':
                # 用户有、AI 没有（漏读）：交给行内插值
                pass
            elif tag == 'insert':
                # AI 有、用户没有（幻觉/多读）：忽略
                pass

        logger.info(f"Alignment stats: {match_stats}")
        unmatched_user_tokens = sum(1 for t in user_char_sequence if t['time'] is None)
        logger.info(
            f"User tokens without direct match (will interpolate): "
            f"{unmatched_user_tokens}"
        )

        # 7. 按行重新组装（插值 + 格式化）
        lines_tokens_map = {i: [] for i in range(len(self.parser.lines_text))}
        for token in user_char_sequence:
            lines_tokens_map[token['line_idx']].append(token)

        current_last_time = 0.0
        for i in range(len(self.parser.lines_text)):
            if stop_event.is_set():
                return ""

            line_tokens = lines_tokens_map[i]
            target_line = self.parser.lines_text[i]

            # 幻觉清洗 + 智能插值
            self._clean_hallucinations(line_tokens)
            self._interpolate_timestamps(line_tokens, current_last_time)

            valid_times = [t['time'] for t in line_tokens if t['time'] is not None]
            if valid_times:
                current_last_time = valid_times[-1]

            # === 强制纠偏 ===
            original_ts = (
                self.parser.lines_timestamps[i]
                if i < len(self.parser.lines_timestamps)
                else -1.0
            )

            next_line_start = None
            if i + 1 < len(self.parser.lines_timestamps):
                next_ts = self.parser.lines_timestamps[i + 1]
                if next_ts > 0:
                    next_line_start = next_ts

            if self.enable_force_calibration and original_ts > 0:
                is_force_calibrated = False

                if not valid_times:
                    if line_tokens:
                        logger.warning(
                            f"Line {i + 1} [Original: {original_ts}s] has NO generated "
                            f"timestamp. Forcing fallback."
                        )
                        for k, t in enumerate(line_tokens):
                            t['time'] = original_ts + (k * 0.25)
                        current_last_time = line_tokens[-1]['time']
                        is_force_calibrated = True
                    else:
                        # 整行没有任何可打轴 token（如纯标点行）：保持原样输出
                        logger.warning(
                            f"Line {i + 1} [Original: {original_ts}s] has no tokens "
                            f"(punctuation-only line?). Skipping force calibration."
                        )
                else:
                    generated_start = valid_times[0]
                    diff = generated_start - original_ts
                    logger.info(
                        f"Line {i + 1}: Orig={original_ts:.2f}s, "
                        f"Gen={generated_start:.2f}s, Diff={diff:.2f}s"
                    )
                    if abs(diff) > self.calibration_threshold:
                        logger.warning(
                            f"Line {i + 1} force calibrated! Diff: {diff:.2f}s"
                        )
                        correction = original_ts - generated_start
                        for t in line_tokens:
                            if t['time'] is not None:
                                t['time'] += correction
                        if line_tokens and line_tokens[-1]['time'] is not None:
                            current_last_time = line_tokens[-1]['time']
                        is_force_calibrated = True

                # 强制边界检查：本行末尾不能越过下一行（空 token 行跳过）
                if not self.enable_avg_distribution and next_line_start and line_tokens:
                    last_token = line_tokens[-1]
                    if (
                        last_token['time']
                        and last_token['time'] > next_line_start - 0.1
                    ):
                        start_time = (
                            line_tokens[0]['time']
                            if line_tokens[0]['time']
                            else original_ts
                        )
                        target_end = next_line_start - 0.1
                        if target_end <= start_time:
                            target_end = start_time + 0.1
                        duration = target_end - start_time
                        token_count = len(line_tokens)
                        step = duration / token_count
                        logger.warning(
                            f"Line {i + 1} overlap detected. Compressing to fit "
                            f"before {next_line_start}s"
                        )
                        for k, t in enumerate(line_tokens):
                            t['time'] = start_time + (k * step)
                        if line_tokens:
                            current_last_time = line_tokens[-1]['time']
                            is_force_calibrated = True

                # 平均分配逻辑
                if is_force_calibrated and self.enable_avg_distribution:
                    logger.info(f"Line {i + 1} applying average distribution.")
                    token_count = len(line_tokens)
                    if token_count > 0:
                        start_time = original_ts
                        target_end = start_time + (token_count * 0.3)
                        if next_line_start:
                            target_end_limit = next_line_start - 0.1
                            if target_end_limit - start_time < 0.2:
                                target_end = start_time + (token_count * 0.25)
                            else:
                                target_end = target_end_limit
                        else:
                            target_end = start_time + (token_count * 0.3)

                        current_shifted_end = line_tokens[-1]['time']
                        if (
                            current_shifted_end
                            and (current_shifted_end - start_time)
                            > (token_count * 0.5)
                        ):
                            potential_end = max(target_end, current_shifted_end)
                            if (
                                next_line_start
                                and potential_end > next_line_start - 0.1
                            ):
                                target_end = next_line_start - 0.1
                            else:
                                target_end = potential_end

                        duration = max(0.2, target_end - start_time)
                        step = duration / token_count
                        for k, t in enumerate(line_tokens):
                            t['time'] = start_time + (k * step)
                        if line_tokens:
                            current_last_time = line_tokens[-1]['time']

            # === 最终硬边界安全检查 ===
            if i + 1 < len(self.parser.lines_timestamps):
                next_ts_limit = self.parser.lines_timestamps[i + 1]
                if next_ts_limit > 0:
                    hard_limit = next_ts_limit - 0.05
                    last_valid_idx = -1
                    last_valid_time = None
                    for k in range(len(line_tokens) - 1, -1, -1):
                        if line_tokens[k]['time'] is not None:
                            last_valid_idx = k
                            last_valid_time = line_tokens[k]['time']
                            break

                    if last_valid_idx != -1 and last_valid_time is not None:
                        if last_valid_time > hard_limit:
                            logger.warning(
                                f"Line {i + 1} final check: "
                                f"End={last_valid_time:.3f}s > "
                                f"Next={next_ts_limit:.3f}s. Compressing..."
                            )
                            start_valid_idx = 0
                            start_t = 0.0
                            for k in range(len(line_tokens)):
                                if line_tokens[k]['time'] is not None:
                                    start_valid_idx = k
                                    start_t = line_tokens[k]['time']
                                    break
                            if start_t >= hard_limit:
                                start_t = max(0, hard_limit - 0.2)

                            duration = hard_limit - start_t
                            if duration < 0.1:
                                duration = 0.1

                            count = last_valid_idx - start_valid_idx + 1
                            if count > 0:
                                step = duration / count
                                for k in range(count):
                                    idx = start_valid_idx + k
                                    line_tokens[idx]['time'] = start_t + (k * step)
                            current_last_time = line_tokens[last_valid_idx]['time']

            # 生成结果行
            line_str, effective_start = self._construct_line_string(
                line_tokens, target_line, 0.0
            )
            output_lines.append(line_str)

            # 翻译行
            if i in self.parser.translations:
                final_time = (
                    effective_start if effective_start is not None else current_last_time
                )
                for trans_text in self.parser.translations[i]:
                    output_lines.append(
                        f"[{format_time(final_time, self.time_offset)}]{trans_text}"
                    )

        return "\n".join(output_lines)

    def _generate_raw_lrc(self, result, stop_event):
        lines = []
        segments = self._get_attr(result, 'segments', [])
        if not segments:
            try:
                segments = list(result)
            except (TypeError, AttributeError) as e:
                logger.debug(f"Could not convert result to list: {e}")
                segments = []
        for seg in segments:
            if stop_event.is_set():
                return ""
            words = self._get_attr(seg, 'words', [])
            if words:
                seg_line = ""
                for w in words:
                    w_text = self._get_attr(w, 'word', '')
                    if not w_text:
                        continue
                    w_start = float(self._get_attr(w, 'start', 0.0) or 0.0)
                    ts_str = format_time(w_start, self.time_offset)
                    clean_w = w_text.strip()
                    if clean_w:
                        seg_line += f"[{ts_str}]{clean_w}"
                if seg_line:
                    lines.append(seg_line)
            else:
                start = self._get_attr(seg, 'start', 0)
                text = self._get_attr(seg, 'text', '').strip()
                if text:
                    lines.append(f"[{format_time(start, self.time_offset)}]{text}")
        return "\n".join(lines)

    def _prepare_user_sequence(self) -> List[Dict[str, Any]]:
        user_char_sequence = []
        for line_idx, line_text in enumerate(self.parser.lines_text):
            tokens = self._tokenize_line(line_text)
            for token in tokens:
                token['line_idx'] = line_idx
                token['clean_text'] = self._clean_token(token['text'])
                user_char_sequence.append(token)
        return user_char_sequence

    def _match_replace_region(self, user_seq, ai_seq, i1, i2, j1, j2, last_valid_time):
        """在 replace 区间内做一层局部序列比对，挽救可匹配 token。"""
        user_slice = [t.get('clean_text', '') for t in user_seq[i1:i2]]
        ai_slice = [t['text'] for t in ai_seq[j1:j2]]
        if not user_slice or not ai_slice:
            return last_valid_time

        sub_matcher = difflib.SequenceMatcher(None, user_slice, ai_slice)
        for tag, si1, si2, sj1, sj2 in sub_matcher.get_opcodes():
            if tag != 'equal':
                continue
            for k in range(si2 - si1):
                user_idx = i1 + si1 + k
                ai_idx = j1 + sj1 + k
                matched_time = ai_seq[ai_idx]['start']
                if matched_time < last_valid_time:
                    matched_time = last_valid_time
                user_seq[user_idx]['time'] = matched_time
                last_valid_time = matched_time
        return last_valid_time

    def _prepare_ai_sequence_tokens(self) -> List[Dict[str, Any]]:
        """生成与用户歌词分词粒度一致的 AI token 序列。

        中文字符逐个成 token，英文/数字保持整词，避免 SequenceMatcher
        在“用户整词 vs AI 单字符”之间无法匹配。
        """
        ai_sequence = []
        for w_obj in self.ai_words_pool:
            text = self._get_attr(w_obj, 'word', "")
            try:
                start = float(self._get_attr(w_obj, 'start', 0.0) or 0.0)
                end = float(self._get_attr(w_obj, 'end', start) or start)
            except (TypeError, ValueError):
                start, end = 0.0, 0.0

            clean_text = self._clean_token(text)
            if not clean_text:
                continue

            tokens = self._tokenize_line(clean_text)
            duration = max(0.0, end - start)
            total_chars = len(clean_text)

            char_cursor = 0
            for token in tokens:
                token_start_offset = clean_text.index(token['text'], char_cursor)
                char_cursor = token_start_offset + len(token['text'])

                if total_chars > 0 and duration > 0:
                    token_start = start + (token_start_offset / total_chars) * duration
                else:
                    token_start = start

                ai_sequence.append({
                    'text': token['text'],
                    'start': token_start,
                    'orig_obj': w_obj,
                })
        return ai_sequence

    def _tokenize_line(self, line):
        """分词函数，将行文本拆分为 token。"""
        tokens = []
        token_iter = re.finditer(
            r"([a-zA-Z0-9']+|[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])",
            line,
        )
        last_end_idx = 0
        for match in token_iter:
            pre_text = line[last_end_idx:match.start()].replace("\n", "")
            token_text = match.group()
            last_end_idx = match.end()
            tokens.append({
                "text": token_text,
                "pre": pre_text,
                "time": None,
                "end_idx": last_end_idx,
            })
        return tokens

    def _extract_words_from_result(self, result):
        self.ai_words_pool = []
        segments = self._get_attr(result, 'segments', [])
        if not segments:
            try:
                segments = list(result)
            except (TypeError, AttributeError) as e:
                logger.debug(f"Could not convert result to list: {e}")
                segments = []

        for seg in segments:
            words = self._get_attr(seg, 'words', [])
            if words:
                self.ai_words_pool.extend(words)
                continue

            # 兜底：无词级时间戳时，按段文本 token 均摊时间
            seg_text = self._get_attr(seg, 'text', '') or ''
            clean_text = self._clean_token(seg_text)
            tokens = self._tokenize_line(clean_text)
            if not tokens:
                continue

            try:
                seg_start = float(self._get_attr(seg, 'start', 0.0) or 0.0)
                seg_end = float(self._get_attr(seg, 'end', seg_start) or seg_start)
            except (TypeError, ValueError):
                seg_start, seg_end = 0.0, 0.0

            duration = max(0.0, seg_end - seg_start)
            total_chars = sum(len(t['text']) for t in tokens)
            char_cursor = 0
            for token in tokens:
                offset = char_cursor
                char_cursor += len(token['text'])
                if total_chars > 0 and duration > 0:
                    token_start = seg_start + (offset / total_chars) * duration
                    token_end = seg_start + (char_cursor / total_chars) * duration
                else:
                    token_start = token_end = seg_start
                self.ai_words_pool.append({
                    'word': token['text'],
                    'start': token_start,
                    'end': token_end,
                })

    def _clean_hallucinations(self, line_tokens):
        count = len(line_tokens)
        if count < 2:
            return

        for k in range(count - 1):
            t1 = line_tokens[k]["time"]
            t2 = None
            for j in range(k + 1, count):
                if line_tokens[j]["time"] is not None:
                    t2 = line_tokens[j]["time"]
                    break

            if t1 is not None and t2 is not None:
                # 同一行内相邻字间隔超过 3 秒视为幻觉
                if t2 - t1 > 3.0:
                    line_tokens[k]["time"] = None

    def _interpolate_timestamps(self, line_tokens, prev_line_end_time):
        count = len(line_tokens)
        for k in range(count):
            if line_tokens[k]["time"] is not None:
                continue

            prev_time = prev_line_end_time
            for j in range(k - 1, -1, -1):
                if line_tokens[j]["time"] is not None:
                    prev_time = line_tokens[j]["time"]
                    break

            next_time = None
            steps_to_next = 0
            for j in range(k + 1, count):
                if line_tokens[j]["time"] is not None:
                    next_time = line_tokens[j]["time"]
                    break
                steps_to_next += 1

            if next_time is not None:
                gap = next_time - prev_time
                if gap > 2.5:
                    # 右吸附策略
                    est_duration = 0.3
                    back_calc_time = next_time - ((steps_to_next + 1) * est_duration)
                    line_tokens[k]["time"] = max(prev_time + 0.1, back_calc_time)
                else:
                    # 平滑插值
                    steps = steps_to_next + 1
                    step_gap = gap / (steps + 1)
                    step_gap = max(MIN_DURATION, min(step_gap, 0.4))
                    line_tokens[k]["time"] = prev_time + step_gap
            else:
                # 左吸附
                line_tokens[k]["time"] = prev_time + 0.25

    def _construct_line_string(self, line_tokens, original_line, last_valid_time):
        if not line_tokens:
            return original_line, None

        line_str = ""
        effective_start_time = None
        current_last_time = last_valid_time

        for k, item in enumerate(line_tokens):
            t = item["time"]
            if t is not None:
                if t < current_last_time or (t == current_last_time and k > 0):
                    t = current_last_time + MIN_DURATION
                current_last_time = t
                item["time"] = t
            else:
                # 理论上插值后不应残留 None；兜底沿用上一个有效时间
                t = current_last_time
                item["time"] = t

            if k == 0:
                effective_start_time = t

            ts_str = format_time(t, self.time_offset)
            tag = f"[{ts_str}]"

            if k == 0 and item["pre"].strip():
                line_str += f"{tag}{item['pre']}{item['text']}"
            else:
                line_str += f"{item['pre']}{tag}{item['text']}"

        last_token = line_tokens[-1]
        line_str += original_line[last_token['end_idx']:]
        return line_str, effective_start_time

    @staticmethod
    def _get_attr(obj, key, default=None):
        """安全获取对象属性或字典值。"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    @lru_cache(maxsize=2048)
    def _clean_token(text):
        """清理 token 文本（去标点、转小写），带缓存。"""
        if not text:
            return ""
        return re.sub(
            r'[^\w\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]',
            '',
            text,
        ).lower()
