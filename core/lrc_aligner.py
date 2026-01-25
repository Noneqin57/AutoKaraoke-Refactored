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
import logging

logger = setup_logger("Worker")

class LrcAligner:
    def __init__(self, parser: LrcParser, time_offset: float = 0.0, enable_force_calibration: bool = True, enable_avg_distribution: bool = False):
        self.parser = parser
        self.time_offset = time_offset
        self.enable_force_calibration = enable_force_calibration
        self.enable_avg_distribution = enable_avg_distribution
        self.ai_words_pool: List[Dict[str, Any]] = []
        self.ai_segments_pool: List[Dict[str, Any]] = [] # 新增：句子级 Segment
        self.pool_cursor = 0
        
    def run(self, whisper_result, stop_event: Event, progress_queue: Queue) -> str:
        """
        执行对齐主逻辑 (全局序列对齐版)
        """
        logger.info("=== Starting LrcAligner Run ===")
        logger.info(f"Input lines count: {len(self.parser.lines_text)}")
        if self.parser.lines_timestamps:
            valid_ts_count = sum(1 for t in self.parser.lines_timestamps if t > 0)
            logger.info(f"Input lines with valid timestamps: {valid_ts_count}/{len(self.parser.lines_timestamps)}")
        
        output_lines = []
        # 添加头部
        for h in self.parser.headers: output_lines.append(h)
        if self.parser.headers: output_lines.append("")
        
        # 1. 提取所有 AI 识别出的单词 (Flattened)
        self._extract_words_from_result(whisper_result)
        logger.info(f"Extracted {len(self.ai_words_pool)} words from Whisper result.")
        
        # 2. 如果没有参考文本，直接输出识别结果
        if not self.parser.lines_text:
            logger.info("No reference text provided. Generating raw LRC.")
            return self._generate_raw_lrc(whisper_result, stop_event)
            
        progress_queue.put("正在执行全局序列对齐...")
        
        # 3. 准备用户输入的全局字符序列 (优化：预先计算)
        user_char_sequence = self._prepare_user_sequence()
        logger.info(f"User char sequence length: {len(user_char_sequence)}")
        
        # 4. 准备 AI 的全局字符序列 (优化：预先计算)
        ai_char_sequence = self._prepare_ai_sequence()
        logger.info(f"AI char sequence length: {len(ai_char_sequence)}")

        # 5. 使用 difflib 进行序列比对 (优化：使用预清洗的字符串)
        user_tokens_str = [t.get('clean_text', '') for t in user_char_sequence]
        ai_tokens_str = [t['text'] for t in ai_char_sequence]
        
        matcher = difflib.SequenceMatcher(None, user_tokens_str, ai_tokens_str)
        logger.info(f"Sequence matching ratio: {matcher.ratio():.4f}")
        
        # 6. 回填时间戳
        last_valid_time = 0.0
        
        match_stats = {'equal': 0, 'replace': 0, 'delete': 0, 'insert': 0}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            match_stats[tag] += (i2 - i1)
            if tag == 'equal':
                # 匹配成功区间
                for k in range(i2 - i1):
                    user_idx = i1 + k
                    ai_idx = j1 + k
                    
                    matched_time = ai_char_sequence[ai_idx]['start']
                    if matched_time < last_valid_time: matched_time = last_valid_time
                    
                    user_char_sequence[user_idx]['time'] = matched_time
                    last_valid_time = matched_time
            elif tag == 'replace':
                # 替换区间 (尝试模糊匹配或者跳过)
                pass
            elif tag == 'delete':
                # 用户有，AI 没有 (漏读) -> 插值处理
                pass
            elif tag == 'insert':
                # AI 有，用户没有 (幻觉/多读) -> 忽略
                pass
        
        logger.info(f"Alignment stats: {match_stats}")
        
        # 7. 重新组装回行 (按行进行插值和格式化)
        # 先按行分组
        lines_tokens_map = {i: [] for i in range(len(self.parser.lines_text))}
        for token in user_char_sequence:
            lines_tokens_map[token['line_idx']].append(token)
            
        current_last_time = 0.0
        
        for i in range(len(self.parser.lines_text)):
            if stop_event.is_set(): return ""
            
            line_tokens = lines_tokens_map[i]
            target_line = self.parser.lines_text[i]
            
            # 幻觉清洗 (虽然全局对齐已经过滤了大部分，但仍需检查时序跳变)
            self._clean_hallucinations(line_tokens)
            
            # 智能插值 (填补 'delete' 和 'replace' 造成的空洞)
            self._interpolate_timestamps(line_tokens, current_last_time)
            
            # 更新 current_last_time
            valid_times = [t['time'] for t in line_tokens if t['time'] is not None]
            if valid_times:
                current_last_time = valid_times[-1]
            
            # === 强制纠偏逻辑 (Force Calibration) ===
            # 如果输入文件包含原始时间戳，我们强制将当前行的起始时间对齐到原始时间
            original_ts = self.parser.lines_timestamps[i] if i < len(self.parser.lines_timestamps) else -1.0
            
            # 关键修正：只要有原始时间戳，无论当前行是否有生成时间，都强制应用
            if self.enable_force_calibration and original_ts > 0:
                is_force_calibrated = False
                correction = 0.0
                
                if not valid_times:
                    logger.warning(f"Line {i+1} [Original: {original_ts}s] has NO generated timestamp. Forcing fallback.")
                    # 如果这一行完全没生成时间（漏读），直接把整个行的时间平移过来
                    # 我们假设第一个字就是 original_ts，后面按节奏铺开
                    base_time = original_ts
                    for k, t in enumerate(line_tokens):
                         t['time'] = base_time + (k * 0.25) # 估算节奏
                    current_last_time = line_tokens[-1]['time']
                    is_force_calibrated = True
                else:
                    # 如果生成了时间，计算偏差
                    generated_start = valid_times[0]
                    diff = generated_start - original_ts
                    
                    logger.info(f"Line {i+1}: Orig={original_ts:.2f}s, Gen={generated_start:.2f}s, Diff={diff:.2f}s")
                    
                    # 降低阈值到 1.5秒，并且只要有偏差就修正
                    if abs(diff) > 1.5:
                        logger.warning(f"Line {i+1} force calibrated! Diff: {diff:.2f}s")
                        correction = original_ts - generated_start
                        for t in line_tokens:
                            if t['time'] is not None:
                                t['time'] += correction
                        
                        # 再次更新 current_last_time
                        if line_tokens and line_tokens[-1]['time'] is not None:
                            current_last_time = line_tokens[-1]['time']
                        
                        is_force_calibrated = True

                # === 强制边界检查 ===
                # 无论是否触发了强制校准，只要有原始时间戳，我们就应该利用下一行的原始时间戳作为硬性约束
                # 以防止本行的时间轴溢出到下一行
                
                next_line_start = None
                if i + 1 < len(self.parser.lines_timestamps):
                    next_ts = self.parser.lines_timestamps[i+1]
                    if next_ts > 0: next_line_start = next_ts

                # 如果没有启用平均分配，我们至少要确保最后一个字不越界
                if not self.enable_avg_distribution and next_line_start:
                    last_token = line_tokens[-1]
                    if last_token['time'] and last_token['time'] > next_line_start - 0.1:
                         # 越界了，尝试整体压缩
                         start_time = line_tokens[0]['time'] if line_tokens[0]['time'] else original_ts
                         # 确保起始时间不晚于结束时间
                         target_end = next_line_start - 0.1
                         if target_end <= start_time: target_end = start_time + 0.1
                         
                         duration = target_end - start_time
                         token_count = len(line_tokens)
                         step = duration / token_count
                         
                         logger.warning(f"Line {i+1} overlap detected. Compressing to fit before {next_line_start}s")
                         
                         for k, t in enumerate(line_tokens):
                             t['time'] = start_time + (k * step)
                         
                         if line_tokens:
                             current_last_time = line_tokens[-1]['time']
                             is_force_calibrated = True # 标记为已修改，虽然不是传统的平移校准

                # === 平均分配逻辑 (Average Distribution) ===
                if is_force_calibrated and self.enable_avg_distribution:
                    logger.info(f"Line {i+1} applying average distribution.")
                    token_count = len(line_tokens)
                    if token_count > 0:
                        start_time = original_ts
                        
                        # 重新计算结束时间 (Target End Time)
                        # 策略：既然触发了平均分配，说明我们不信任 AI 的内部时间结构
                        # 我们优先使用“下一行的开始时间”作为当前行的界限，以填满空隙
                        # 如果没有下一行时间，则使用字符数估算
                        
                        # 1. 尝试使用下一行的开始时间作为参考
                        target_end = start_time + (token_count * 0.3) # Default fallback
                        
                        if next_line_start:
                            # 留出 0.1s 间隙
                            target_end_limit = next_line_start - 0.1
                            
                            # 如果计算出的持续时间太短（比如两句话重叠了），则回退到估算
                            if target_end_limit - start_time < 0.2: 
                                target_end = start_time + (token_count * 0.25)
                            else:
                                target_end = target_end_limit
                        else:
                            # 2. 没有下一行参考，直接根据字数估算 (0.3s 一个字，比较宽松)
                            target_end = start_time + (token_count * 0.3)
                            
                        # 3. 检查 AI 原始生成的结束时间 (Shifted)
                        # 如果 AI 生成的 duration 明显比我们估算的要长（说明唱得很慢），那保留 AI 的长度可能更好？
                        # 但在“强制纠偏”场景下，通常意味着 AI 时间轴乱了，所以更倾向于规整化。
                        # 这里我们只做一个最小长度检查：
                        
                        current_shifted_end = line_tokens[-1]['time']
                        if current_shifted_end and (current_shifted_end - start_time) > (token_count * 0.5):
                             # 如果 AI 认为这句话特别长（平均每字 > 0.5s），可能它是对的，取两者最大值
                             # 但前提是不能超过 next_line_start
                             potential_end = max(target_end, current_shifted_end)
                             if next_line_start and potential_end > next_line_start - 0.1:
                                 target_end = next_line_start - 0.1
                             else:
                                 target_end = potential_end

                        duration = max(0.2, target_end - start_time)
                        step = duration / token_count
                        
                        for k, t in enumerate(line_tokens):
                            t['time'] = start_time + (k * step)
                        
                        if line_tokens:
                            current_last_time = line_tokens[-1]['time']
            
            # === Final Hard Boundary Safety Check (Universal) ===
            # 无论前面经过了什么处理 (AI生成/强制校准/平均分配)，最后一道防线确保不越界
            if i + 1 < len(self.parser.lines_timestamps):
                next_ts_limit = self.parser.lines_timestamps[i+1]
                if next_ts_limit > 0:
                    hard_limit = next_ts_limit - 0.05 # 留出 50ms 间隙
                    
                    # 寻找最后一个有效的时间戳 (防止末尾有 None)
                    last_valid_idx = -1
                    last_valid_time = None
                    for k in range(len(line_tokens)-1, -1, -1):
                        if line_tokens[k]['time'] is not None:
                            last_valid_idx = k
                            last_valid_time = line_tokens[k]['time']
                            break
                    
                    if last_valid_idx != -1 and last_valid_time is not None:
                         # 检查是否越界
                         if last_valid_time > hard_limit:
                             logger.warning(f"Line {i+1} final check: End={last_valid_time:.3f}s > Next={next_ts_limit:.3f}s. Compressing...")
                             
                             # 确定起始时间 (使用第一个有效时间)
                             start_valid_idx = 0
                             start_t = 0.0
                             for k in range(len(line_tokens)):
                                 if line_tokens[k]['time'] is not None:
                                     start_valid_idx = k
                                     start_t = line_tokens[k]['time']
                                     break
                             
                             # 如果起始时间本身就晚于限制，那说明上一行可能就有问题，或者这行本身有问题
                             if start_t >= hard_limit: 
                                 # 强制回退起始时间，尽量保留 0.2s 的持续时间
                                 start_t = max(0, hard_limit - 0.2)
                             
                             duration = hard_limit - start_t
                             if duration < 0.1: duration = 0.1
                             
                             # 重新分配时间 (只针对 start_valid_idx 到 last_valid_idx 之间的有效token)
                             # 为了简单，我们对这段区间内的所有token重新插值
                             # 注意：这里我们覆盖所有 token，包括中间可能是 None 的
                             
                             count = last_valid_idx - start_valid_idx + 1
                             if count > 0:
                                 step = duration / count
                                 for k in range(count):
                                     idx = start_valid_idx + k
                                     line_tokens[idx]['time'] = start_t + (k * step)
                             
                             current_last_time = line_tokens[last_valid_idx]['time']

            # 生成结果行
            line_str, effective_start = self._construct_line_string(line_tokens, target_line, 0.0) # last_valid_time 已在内部处理
            output_lines.append(line_str)
            
            # 处理翻译行
            if i in self.parser.translations:
                final_time = effective_start if effective_start is not None else current_last_time
                for trans_text in self.parser.translations[i]:
                    output_lines.append(f"[{format_time(final_time, self.time_offset)}]{trans_text}")
                    
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

    def _tokenize_line(self, line):
        """分词函数，将行文本拆分为token"""
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

    def _extract_words_from_result(self, result):
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

    def _map_lines_to_segments(self, lines: List[str]) -> Dict[int, int]:
        """
        建立 User Line Index -> AI Segment Index 的映射
        """
        mapping = {}
        ai_texts = [self._get_attr(s, 'text', '').strip() for s in self.ai_segments_pool]
        
        # 简单的一对一或多对一匹配
        # 这里使用 difflib 寻找最相似的句子
        # 注意：Whisper 的分句可能和 LRC 行不完全一致（可能一句LRC对应两句Whisper，反之亦然）
        # 这里实现一个简单的贪心匹配算法
        
        ai_cursor = 0
        for i, line in enumerate(lines):
            best_ratio = 0.0
            best_idx = -1
            
            # 在 ai_cursor 附近搜索
            search_range = 3 # 向后搜索 3 句
            for offset in range(search_range):
                curr = ai_cursor + offset
                if curr >= len(ai_texts): break
                
                ratio = difflib.SequenceMatcher(None, line, ai_texts[curr]).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = curr
            
            if best_ratio > 0.3: # 阈值
                mapping[i] = best_idx
                ai_cursor = best_idx # 允许同一句 Whisper 对应多行 LRC (不推进 cursor)，或者推进一步
                # 如果匹配度很高，通常意味着这句话被消耗了，但考虑到长句可能被拆分，我们保守推进
                if best_idx == ai_cursor:
                    pass # 留在当前句
                else:
                    ai_cursor = best_idx
            else:
                # 如果没匹配上，可能沿用上一个 Segment，或者暂时不约束
                pass
                
        return mapping

    def _match_time_for_line(self, line_tokens, search_window, last_valid_time, seg_start_constraint, seg_end_constraint):
        total_ai_words = len(self.ai_words_pool)
        
        current_dynamic_window = search_window
        consecutive_matches = 0

        for token in line_tokens:
            user_clean = self._clean_token(token['text'])
            matched_time = None
            
            if consecutive_matches > 3:
                current_dynamic_window = max(5, search_window // 2)
            else:
                current_dynamic_window = search_window

            found_in_window = False
            
            # 优先在约束范围内搜索
            # 我们需要找到 pool_cursor 之后，且时间在 [seg_start, seg_end] 范围内的单词
            
            for offset in range(current_dynamic_window):
                if self.pool_cursor + offset >= total_ai_words: break
                
                ai_w_obj = self.ai_words_pool[self.pool_cursor + offset]
                w_start = self._get_attr(ai_w_obj, 'start', 0.0)
                
                # 核心约束逻辑：
                # 1. 单词时间必须 >= 上一个有效时间 (保持时序)
                # 2. 如果有 Segment 约束，单词时间最好在 Segment 范围内 (允许少量误差)
                # 3. 如果单词时间远远超过了 Segment 结束时间，说明可能漂移到了下一句，应拒绝
                
                is_time_valid = True
                if w_start < last_valid_time - 0.5: is_time_valid = False
                
                # 如果当前单词时间比 Segment 结束时间晚太多（比如 > 1秒），则认为是下一句的词
                if seg_end_constraint != float('inf') and w_start > seg_end_constraint + 1.0:
                    is_time_valid = False
                
                # 如果单词时间比 Segment 开始时间早太多，也不对
                if w_start < seg_start_constraint - 1.0:
                    is_time_valid = False

                if is_time_valid:
                    ai_text = self._get_attr(ai_w_obj, 'word', "")
                    ai_clean = self._clean_token(ai_text)
                    
                    if user_clean and ai_clean and (user_clean in ai_clean or ai_clean in user_clean):
                        matched_time = w_start
                        self.pool_cursor = self.pool_cursor + offset + 1
                        found_in_window = True
                        break
            
            # (省略掉之前的“紧急扩大窗口”逻辑，因为有了 Segment 约束，乱跑的概率降低，不需要盲目扩大搜索)

            if found_in_window:
                consecutive_matches += 1
            else:
                consecutive_matches = 0
            
            token['time'] = matched_time
        return last_valid_time

    def _clean_hallucinations(self, line_tokens):
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
                if t2 - t1 > 3.0:
                    line_tokens[k]["time"] = None

    def _interpolate_timestamps(self, line_tokens, prev_line_end_time):
        count = len(line_tokens)
        for k in range(count):
            if line_tokens[k]["time"] is None:
                # 找前一个锚点
                prev_time = prev_line_end_time
                for j in range(k - 1, -1, -1):
                    if line_tokens[j]["time"] is not None:
                        prev_time = line_tokens[j]["time"]
                        break
                
                # 找后一个锚点
                next_time = None
                steps_to_next = 0
                for j in range(k + 1, count):
                    if line_tokens[j]["time"] is not None:
                        next_time = line_tokens[j]["time"]
                        break
                    steps_to_next += 1
                
                # 插值逻辑
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
