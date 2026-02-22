# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Any, Optional
from multiprocessing import Queue, Event
from functools import lru_cache

from config import MIN_DURATION
from utils.time_utils import format_time
from utils.logger import setup_logger
from core.lrc_parser import LrcParser

import difflib

logger = setup_logger("Worker")

class LrcAligner:
    # === 对齐调参常量 ===
    # 强制校准：无时间戳行的字间距估算 (秒/字)
    FALLBACK_CHAR_INTERVAL: float = 0.25
    # 强制校准触发阈值：偏差超过此值才校准 (秒)
    FORCE_CALIBRATION_THRESHOLD: float = 1.5
    # 行边界安全间隙 (秒)
    LINE_BOUNDARY_GAP: float = 0.1
    # 最终硬边界安全间隙 (秒)
    HARD_BOUNDARY_GAP: float = 0.05
    # 硬边界压缩：起始时间回退余量 (秒)
    HARD_BOUNDARY_FALLBACK_DURATION: float = 0.2
    # 硬边界压缩：最小持续时间 (秒)
    HARD_BOUNDARY_MIN_DURATION: float = 0.1
    # 平均分配：默认每字持续时间 (秒)
    AVG_CHAR_DURATION: float = 0.3
    # 平均分配：窄间距回退的每字持续时间 (秒)
    AVG_CHAR_DURATION_NARROW: float = 0.25
    # 平均分配：最小有效区间宽度 (秒)
    AVG_MIN_INTERVAL: float = 0.2
    # 平均分配：AI "慢唱"判定阈值 (秒/字)
    AVG_SLOW_THRESHOLD: float = 0.5
    # 平均分配：最小持续时间 (秒)
    AVG_MIN_DURATION: float = 0.2
    # 幻觉清洗：同行内两字间距阈值 (秒)
    HALLUCINATION_GAP_THRESHOLD: float = 3.0
    # 插值：右吸附触发间距阈值 (秒)
    INTERPOLATION_LARGE_GAP: float = 2.5
    # 插值：右吸附估算字持续时间 (秒)
    INTERPOLATION_EST_CHAR_DURATION: float = 0.3
    # 插值：右吸附最小前向间距 (秒)
    INTERPOLATION_MIN_FORWARD_GAP: float = 0.1
    # 插值：平滑插值最大步长 (秒)
    INTERPOLATION_MAX_STEP: float = 0.4
    # 插值：无后续锚点的左吸附步长 (秒)
    INTERPOLATION_LEFT_ATTACH_STEP: float = 0.25

    def __init__(self, parser: LrcParser, time_offset: float = 0.0, enable_force_calibration: bool = True, enable_avg_distribution: bool = False):
        self.parser = parser
        self.time_offset = time_offset
        self.enable_force_calibration = enable_force_calibration
        self.enable_avg_distribution = enable_avg_distribution
        self.ai_words_pool: List[Dict[str, Any]] = []
        self.ai_segments_pool: List[Dict[str, Any]] = [] # 新增：句子级 Segment
        self.pool_cursor = 0
        
    def run(self, whisper_result: Any, stop_event: Event, progress_queue: Queue) -> str:
        """执行对齐主逻辑 (全局序列对齐版)"""
        logger.info("=== Starting LrcAligner Run ===")
        logger.info(f"Input lines count: {len(self.parser.lines_text)}")
        if self.parser.lines_timestamps:
            valid_ts_count = sum(1 for t in self.parser.lines_timestamps if t > 0)
            logger.info(f"Input lines with valid timestamps: {valid_ts_count}/{len(self.parser.lines_timestamps)}")

        output_lines = list(self.parser.headers)
        if self.parser.headers:
            output_lines.append("")

        # 1. 提取所有 AI 识别出的单词
        self._extract_words_from_result(whisper_result)
        logger.info(f"Extracted {len(self.ai_words_pool)} words from Whisper result.")

        # 2. 如果没有参考文本，直接输出识别结果
        if not self.parser.lines_text:
            logger.info("No reference text provided. Generating raw LRC.")
            return self._generate_raw_lrc(whisper_result, stop_event)

        progress_queue.put("正在执行全局序列对齐...")

        # 3. 准备序列并执行全局对齐
        user_char_sequence = self._prepare_user_sequence()
        ai_char_sequence = self._prepare_ai_sequence()
        logger.info(f"User char sequence length: {len(user_char_sequence)}")
        logger.info(f"AI char sequence length: {len(ai_char_sequence)}")

        self._backfill_timestamps_from_alignment(user_char_sequence, ai_char_sequence)

        # 4. 按行分组并逐行处理
        lines_tokens_map = self._group_tokens_by_line(user_char_sequence)
        current_last_time = 0.0

        for i in range(len(self.parser.lines_text)):
            if stop_event.is_set():
                return ""

            line_tokens = lines_tokens_map[i]
            target_line = self.parser.lines_text[i]

            # 清洗、插值、校准
            current_last_time = self._process_line_timestamps(i, line_tokens, current_last_time)

            # 最终硬边界安全检查
            current_last_time = self._enforce_hard_boundary(i, line_tokens, current_last_time)

            # 生成结果行
            line_str, effective_start = self._construct_line_string(line_tokens, target_line, 0.0)
            output_lines.append(line_str)

            # 处理翻译行
            self._append_translation_lines(output_lines, i, effective_start, current_last_time)

        return "\n".join(output_lines)

    def _backfill_timestamps_from_alignment(
        self,
        user_char_sequence: List[Dict[str, Any]],
        ai_char_sequence: List[Dict[str, Any]],
    ) -> None:
        """使用 difflib 序列比对回填时间戳"""
        user_tokens_str = [t.get('clean_text', '') for t in user_char_sequence]
        ai_tokens_str = [t['text'] for t in ai_char_sequence]

        matcher = difflib.SequenceMatcher(None, user_tokens_str, ai_tokens_str, autojunk=False)
        logger.info(f"Sequence matching ratio: {matcher.ratio():.4f}")

        last_valid_time = 0.0
        match_stats = {'equal': 0, 'replace': 0, 'delete': 0, 'insert': 0}

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            match_stats[tag] += (i2 - i1)
            if tag == 'equal':
                for k in range(i2 - i1):
                    user_idx = i1 + k
                    ai_idx = j1 + k
                    matched_time = ai_char_sequence[ai_idx]['start']
                    if matched_time < last_valid_time:
                        matched_time = last_valid_time
                    user_char_sequence[user_idx]['time'] = matched_time
                    last_valid_time = matched_time

        logger.info(f"Alignment stats: {match_stats}")

    def _group_tokens_by_line(self, user_char_sequence: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        """按行索引分组 token"""
        lines_tokens_map: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(len(self.parser.lines_text))}
        for token in user_char_sequence:
            lines_tokens_map[token['line_idx']].append(token)
        return lines_tokens_map

    def _get_next_line_start(self, line_idx: int) -> Optional[float]:
        """获取下一行的有效起始时间戳"""
        if line_idx + 1 < len(self.parser.lines_timestamps):
            next_ts = self.parser.lines_timestamps[line_idx + 1]
            if next_ts > 0:
                return next_ts
        return None

    def _process_line_timestamps(
        self,
        line_idx: int,
        line_tokens: List[Dict[str, Any]],
        current_last_time: float,
    ) -> float:
        """处理单行的时间戳：清洗、插值、强制校准、平均分配

        Returns:
            更新后的 current_last_time
        """
        # 幻觉清洗
        self._clean_hallucinations(line_tokens)
        # 智能插值
        self._interpolate_timestamps(line_tokens, current_last_time)

        # 更新 current_last_time
        valid_times = [t['time'] for t in line_tokens if t['time'] is not None]
        if valid_times:
            current_last_time = valid_times[-1]

        # === 强制纠偏逻辑 (Force Calibration) ===
        original_ts = self.parser.lines_timestamps[line_idx] if line_idx < len(self.parser.lines_timestamps) else -1.0

        if not (self.enable_force_calibration and original_ts > 0):
            return current_last_time

        is_force_calibrated = False

        if not valid_times:
            logger.warning(f"Line {line_idx+1} [Original: {original_ts}s] has NO generated timestamp. Forcing fallback.")
            base_time = original_ts
            for k, t in enumerate(line_tokens):
                 t['time'] = base_time + (k * self.FALLBACK_CHAR_INTERVAL)
            current_last_time = line_tokens[-1]['time']
            is_force_calibrated = True
        else:
            generated_start = valid_times[0]
            diff = generated_start - original_ts
            logger.info(f"Line {line_idx+1}: Orig={original_ts:.2f}s, Gen={generated_start:.2f}s, Diff={diff:.2f}s")

            if abs(diff) > self.FORCE_CALIBRATION_THRESHOLD:
                logger.warning(f"Line {line_idx+1} force calibrated! Diff: {diff:.2f}s")
                correction = original_ts - generated_start
                for t in line_tokens:
                    if t['time'] is not None:
                        t['time'] += correction
                if line_tokens and line_tokens[-1]['time'] is not None:
                    current_last_time = line_tokens[-1]['time']
                is_force_calibrated = True

        # === 强制边界检查 ===
        next_line_start = self._get_next_line_start(line_idx)

        if not self.enable_avg_distribution and next_line_start:
            last_token = line_tokens[-1]
            if last_token['time'] and last_token['time'] > next_line_start - self.LINE_BOUNDARY_GAP:
                 start_time = line_tokens[0]['time'] if line_tokens[0]['time'] else original_ts
                 target_end = next_line_start - self.LINE_BOUNDARY_GAP
                 if target_end <= start_time:
                     target_end = start_time + self.LINE_BOUNDARY_GAP

                 duration = target_end - start_time
                 token_count = len(line_tokens)
                 step = duration / token_count

                 logger.warning(f"Line {line_idx+1} overlap detected. Compressing to fit before {next_line_start}s")

                 for k, t in enumerate(line_tokens):
                     t['time'] = start_time + (k * step)

                 if line_tokens:
                     current_last_time = line_tokens[-1]['time']
                     is_force_calibrated = True

        # === 平均分配逻辑 (Average Distribution) ===
        if is_force_calibrated and self.enable_avg_distribution:
            current_last_time = self._apply_average_distribution(
                line_idx, line_tokens, original_ts, next_line_start
            )

        return current_last_time

    def _apply_average_distribution(
        self,
        line_idx: int,
        line_tokens: List[Dict[str, Any]],
        original_ts: float,
        next_line_start: Optional[float],
    ) -> float:
        """对行内 token 应用平均分配策略

        Returns:
            更新后的 current_last_time
        """
        logger.info(f"Line {line_idx+1} applying average distribution.")
        token_count = len(line_tokens)
        if token_count == 0:
            return 0.0

        start_time = original_ts
        target_end = start_time + (token_count * self.AVG_CHAR_DURATION)

        if next_line_start:
            target_end_limit = next_line_start - self.LINE_BOUNDARY_GAP
            if target_end_limit - start_time < self.AVG_MIN_INTERVAL:
                target_end = start_time + (token_count * self.AVG_CHAR_DURATION_NARROW)
            else:
                target_end = target_end_limit
        else:
            target_end = start_time + (token_count * self.AVG_CHAR_DURATION)

        current_shifted_end = line_tokens[-1]['time']
        if current_shifted_end and (current_shifted_end - start_time) > (token_count * self.AVG_SLOW_THRESHOLD):
             potential_end = max(target_end, current_shifted_end)
             if next_line_start and potential_end > next_line_start - self.LINE_BOUNDARY_GAP:
                 target_end = next_line_start - self.LINE_BOUNDARY_GAP
             else:
                 target_end = potential_end

        duration = max(self.AVG_MIN_DURATION, target_end - start_time)
        step = duration / token_count

        for k, t in enumerate(line_tokens):
            t['time'] = start_time + (k * step)

        return line_tokens[-1]['time'] if line_tokens else 0.0

    def _enforce_hard_boundary(
        self,
        line_idx: int,
        line_tokens: List[Dict[str, Any]],
        current_last_time: float,
    ) -> float:
        """最终硬边界安全检查，确保不越界到下一行

        Returns:
            更新后的 current_last_time
        """
        if line_idx + 1 >= len(self.parser.lines_timestamps):
            return current_last_time

        next_ts_limit = self.parser.lines_timestamps[line_idx + 1]
        if next_ts_limit <= 0:
            return current_last_time

        hard_limit = next_ts_limit - self.HARD_BOUNDARY_GAP

        # 寻找最后一个有效的时间戳
        last_valid_idx = -1
        last_valid_time = None
        for k in range(len(line_tokens) - 1, -1, -1):
            if line_tokens[k]['time'] is not None:
                last_valid_idx = k
                last_valid_time = line_tokens[k]['time']
                break

        if last_valid_idx == -1 or last_valid_time is None:
            return current_last_time

        if last_valid_time <= hard_limit:
            return current_last_time

        logger.warning(f"Line {line_idx+1} final check: End={last_valid_time:.3f}s > Next={next_ts_limit:.3f}s. Compressing...")

        # 确定起始时间
        start_valid_idx = 0
        start_t = 0.0
        for k in range(len(line_tokens)):
            if line_tokens[k]['time'] is not None:
                start_valid_idx = k
                start_t = line_tokens[k]['time']
                break

        if start_t >= hard_limit:
            start_t = max(0, hard_limit - self.HARD_BOUNDARY_FALLBACK_DURATION)

        duration = hard_limit - start_t
        if duration < self.HARD_BOUNDARY_MIN_DURATION:
            duration = self.HARD_BOUNDARY_MIN_DURATION

        count = last_valid_idx - start_valid_idx + 1
        if count > 0:
            step = duration / count
            for k in range(count):
                idx = start_valid_idx + k
                line_tokens[idx]['time'] = start_t + (k * step)

        return line_tokens[last_valid_idx]['time']

    def _append_translation_lines(
        self,
        output_lines: List[str],
        line_idx: int,
        effective_start: Optional[float],
        current_last_time: float,
    ) -> None:
        """追加翻译行到输出"""
        if line_idx in self.parser.translations:
            final_time = effective_start if effective_start is not None else current_last_time
            for trans_text in self.parser.translations[line_idx]:
                output_lines.append(f"[{format_time(final_time, self.time_offset)}]{trans_text}")

    def _generate_raw_lrc(self, result: Any, stop_event: Event) -> str:
        """无参考文本时，直接输出 Whisper 识别结果为 LRC"""
        lines = []
        segments = self._get_attr(result, 'segments', [])
        if not segments:
            try:
                segments = list(result)
            except (TypeError, AttributeError) as e:
                logger.debug(f"Could not convert result to list: {e}")
                segments = []
        for seg in segments:
            if stop_event.is_set(): return ""
            start = self._get_attr(seg, 'start', 0)
            text = self._get_attr(seg, 'text', '').strip()
            if text: lines.append(f"[{format_time(start, self.time_offset)}]{text}")
        return "\n".join(lines)
    
    def _prepare_user_sequence(self) -> List[Dict[str, Any]]:
        """预处理用户字符序列，避免重复计算
        
        Returns:
            用户字符序列列表
        """
        user_char_sequence = []
        for line_idx, line_text in enumerate(self.parser.lines_text):
            tokens = self._tokenize_line(line_text)
            for token in tokens:
                token['line_idx'] = line_idx
                token['clean_text'] = self._clean_token(token['text'])
                user_char_sequence.append(token)
        return user_char_sequence
    
    def _prepare_ai_sequence(self) -> List[Dict[str, Any]]:
        """预处理AI字符序列，避免重复计算
        
        Returns:
            AI字符序列列表
        """
        ai_char_sequence = []
        for w_obj in self.ai_words_pool:
            text = self._get_attr(w_obj, 'word', "")
            start = self._get_attr(w_obj, 'start', 0.0)
            end = self._get_attr(w_obj, 'end', 0.0)
            clean_text = self._clean_token(text)
            
            if clean_text:
                char_list = list(clean_text)
                duration = end - start
                char_duration = duration / len(char_list) if len(char_list) > 0 else 0
                
                for i, char in enumerate(char_list):
                    char_time = start + (i * char_duration)
                    ai_char_sequence.append({
                        'text': char,
                        'start': char_time,
                        'orig_obj': w_obj
                    })
        return ai_char_sequence

    def _tokenize_line(self, line: str) -> List[Dict[str, Any]]:
        """将行文本拆分为 token（CJK 按字、英文按词）"""
        tokens = []
        token_iter = re.finditer(r'([a-zA-Z0-9\']+|[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])', line)
        last_end_idx = 0
        for match in token_iter:
            pre_text = line[last_end_idx:match.start()].replace("\n", "")
            token_text = match.group()
            last_end_idx = match.end()
            tokens.append({
                "text": token_text,
                "pre": pre_text,
                "time": None,
                "end_idx": last_end_idx
            })
        return tokens

    def _extract_words_from_result(self, result: Any) -> None:
        """从 Whisper 结果中提取所有单词和句子级 Segment"""
        self.ai_words_pool = []
        self.ai_segments_pool = []
        segments = self._get_attr(result, 'segments', [])
        if not segments:
            try:
                segments = list(result)
            except (TypeError, AttributeError) as e:
                logger.debug(f"Could not convert result to list: {e}")
                segments = []
            
        for seg in segments:
            self.ai_segments_pool.append(seg) # 保存句子级信息
            words = self._get_attr(seg, 'words', [])
            if words: self.ai_words_pool.extend(words)

    def _clean_hallucinations(self, line_tokens: List[Dict[str, Any]]) -> None:
        """清洗行内时间跳变的幻觉时间戳"""
        count = len(line_tokens)
        if count < 2: return
        
        for k in range(count - 1):
            t1 = line_tokens[k]["time"]
            t2 = None
            # 寻找下一个已知时间的字
            for j in range(k + 1, count):
                if line_tokens[j]["time"] is not None:
                    t2 = line_tokens[j]["time"]
                    break
            
            if t1 is not None and t2 is not None:
                # 如果同一行内两字间隔超过 3秒，且 t1 可能是幻觉
                if t2 - t1 > self.HALLUCINATION_GAP_THRESHOLD:
                    line_tokens[k]["time"] = None

    def _interpolate_timestamps(self, line_tokens: List[Dict[str, Any]], prev_line_end_time: float) -> None:
        """对行内缺失时间戳的 token 进行智能插值

        预先构建锚点索引，O(n) 完成插值，而非每个缺失 token 都线性搜索。
        """
        count = len(line_tokens)
        if count == 0:
            return

        # 预构建: 每个位置对应的下一个有效锚点索引
        next_anchor = [None] * count
        last_anchor_idx = None
        for i in range(count - 1, -1, -1):
            if line_tokens[i]["time"] is not None:
                last_anchor_idx = i
            next_anchor[i] = last_anchor_idx

        # 遍历插值
        prev_time = prev_line_end_time
        for k in range(count):
            if line_tokens[k]["time"] is not None:
                prev_time = line_tokens[k]["time"]
                continue

            # 后锚点
            na_idx = next_anchor[k]
            next_time = line_tokens[na_idx]["time"] if na_idx is not None else None
            steps_to_next = (na_idx - k - 1) if na_idx is not None else 0

            # 插值逻辑
            if next_time is not None:
                gap = next_time - prev_time
                if gap > self.INTERPOLATION_LARGE_GAP:
                    est_duration = self.INTERPOLATION_EST_CHAR_DURATION
                    back_calc_time = next_time - ((steps_to_next + 1) * est_duration)
                    line_tokens[k]["time"] = max(prev_time + self.INTERPOLATION_MIN_FORWARD_GAP, back_calc_time)
                else:
                    steps = steps_to_next + 1
                    step_gap = gap / (steps + 1)
                    step_gap = max(MIN_DURATION, min(step_gap, self.INTERPOLATION_MAX_STEP))
                    line_tokens[k]["time"] = prev_time + step_gap
            else:
                line_tokens[k]["time"] = prev_time + self.INTERPOLATION_LEFT_ATTACH_STEP

            prev_time = line_tokens[k]["time"]

    def _construct_line_string(
        self,
        line_tokens: List[Dict[str, Any]],
        original_line: str,
        last_valid_time: float,
    ) -> tuple[str, Optional[float]]:
        """将 token 列表组装为带时间标签的 LRC 行"""
        if not line_tokens:
            return original_line, None
            
        line_str = ""
        effective_start_time = None
        
        current_last_time = last_valid_time
        
        for k, item in enumerate(line_tokens):
            t = item["time"]
            if t is not None: # Ensure t is not None
                if t <= current_last_time: 
                    t = current_last_time + MIN_DURATION
                current_last_time = t
                item["time"] = t # Write back corrected time
            
            if k == 0: effective_start_time = t
            
            # Format time, handling None safely if logic failed somewhere
            ts_str = format_time(t, self.time_offset) if t is not None else "00:00.00"
            tag = f"[{ts_str}]"
            
            if k == 0 and item["pre"].strip():
                line_str += f"{tag}{item['pre']}{item['text']}"
            else:
                line_str += f"{item['pre']}{tag}{item['text']}"
        
        # 补全行尾剩余字符
        last_token = line_tokens[-1]
        line_str += original_line[last_token['end_idx']:]
        
        return line_str, effective_start_time

    @staticmethod
    def _get_attr(obj, key, default=None):
        """安全获取对象属性或字典值"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    @lru_cache(maxsize=2048)
    def _clean_token(text):
        """清理token文本，使用缓存优化性能
        
        Args:
            text: 输入文本
            
        Returns:
            清理后的小写文本
        """
        if not text:
            return ""
        return re.sub(r'[^\w\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]', '', text).lower()
