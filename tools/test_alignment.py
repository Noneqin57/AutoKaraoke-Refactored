# -*- coding: utf-8 -*-
"""REATK 逐字歌词对齐自动化测试

复用 REATK 后端（core/whisper_worker 同款调用链路）：
  1) stable_whisper.load_model("small", download_root=models)
  2) model.align(audio, preprocess_cjk_spaces(ref_text), language="zh",
                 suppress_silence=True, regroup=False)   # 结构化强制对齐
  3) LrcAligner(parser, ...).run(result, stop_event, progress)  # 逐字 LRC 合成
  4) 输出 {song}/generated.lrc

评估：与 testdata 中下载的 word.lrc（QQ 音乐逐字真值）对比
  - 字符覆盖率（文本一致度）
  - 匹配字符的时间误差：mean / median / std / P90
  - 容差命中率：|Δt| < 100ms / 250ms / 500ms 的字符占比
  - 全局偏置（median Δt，衡量音频起点系统偏差）
  - 逐行平均误差表（识别无声的卡拉OK字幕行/前奏行）

用法（必须用 .venv，含 torch/stable_whisper）：
  .venv\\Scripts\\python.exe tools\\test_alignment.py            # 全量
  .venv\\Scripts\\python.exe tools\\test_alignment.py --limit 2 # 前 2 首
  .venv\\Scripts\\python.exe tools\\test_alignment.py --force   # 强制重跑
"""
import sys
import os
import json
import time
import difflib
import re
import argparse

# 确保项目根目录在 import 路径上（与 tools/collect_test_data.py 一致）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pathlib import Path

from core.lrc_parser import LrcParser
from core.lrc_aligner_v2 import LrcAligner
from core.whisper_worker import preprocess_cjk_spaces

# ---- 后端依赖（.venv 内）----
import torch
import stable_whisper
from multiprocessing import Event

LANGUAGE = "zh"
MIN_AUDIO_SIZE = 200 * 1024  # 200KB 以下视为无效音频
MIN_DURATION = 0.06  # 与 config.MIN_DURATION 一致的最小时间间隔（秒）

_TS_RE = re.compile(r"\[(\d+):(\d+\.\d+)\]")


class _ProgressSink:
    """对齐器的 progress_queue 占位（忽略进度消息，避免依赖 GUI 队列）"""

    def put(self, msg):
        pass


def parse_word_lrc(content):
    """解析逐字 LRC（行首 [mm:ss.mmm] + 内联 [mm:ss.mmm]字符 格式）

    返回: List[line]，每行为 List[(char, start_ms, end_ms)]
    """
    lines = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line.startswith("["):
            continue
        parts = list(_TS_RE.finditer(line))
        if not parts:
            continue
        tokens = []
        for idx, pm in enumerate(parts):
            start_ms = int(pm.group(1)) * 60000 + int(round(float(pm.group(2)) * 1000))
            text_start = pm.end()
            text_end = parts[idx + 1].start() if idx + 1 < len(parts) else len(line)
            text = line[text_start:text_end]
            # 内联时间戳后面紧跟的文本可能为空（句末），跳过
            if not text:
                continue
            for ch in text:
                tokens.append((ch, start_ms))
        lines.append(tokens)
    return lines


def compare_gt_generated(gt_content, gen_content):
    """逐字时间戳对比：全局字符序列 difflib 对齐

    返回指标 dict：
      gt_chars / matched_chars / coverage
      delta_ms: 全部匹配字符的 gen-gt 差值（ms），用于 bias/分布
      abs_errors_ms: |gen-gt| 列表
      line_errors_ms: 每行（GT 行序）匹配字符的平均 |Δt|，无匹配行为 None
    """
    gt_lines = parse_word_lrc(gt_content)
    gen_lines = parse_word_lrc(gen_content)

    # 展平为 (char, start_ms, line_idx)
    gt_chars = [(c, t, li) for li, toks in enumerate(gt_lines) for c, t in toks]
    gen_chars = [(c, t, li) for li, toks in enumerate(gen_lines) for c, t in toks]

    if not gt_chars:
        return {"gt_chars": 0, "matched_chars": 0, "coverage": 0.0}

    gt_seq = [c for c, _, _ in gt_chars]
    gen_seq = [c for c, _, _ in gen_chars]

    matched = []
    sm = difflib.SequenceMatcher(None, gt_seq, gen_seq, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                _, gt_t, gt_li = gt_chars[i1 + k]
                _, gen_t, _ = gen_chars[j1 + k]
                matched.append((gt_t, gen_t, gt_li))

    if not matched:
        return {
            "gt_chars": len(gt_chars),
            "matched_chars": 0,
            "coverage": 0.0,
            "delta_ms": [],
            "abs_errors_ms": [],
            "line_errors_ms": [None] * len(gt_lines),
        }

    # 注意：这里必须从元组显式解包 t/g（不能用 `for _, gen_t, _ in matched`，
    # 否则推导式中 gt_t 是自由变量，引用外层循环残留的最后一个 GT 时间戳，
    # 导致所有 delta 被整体平移）。见 debug_scope.py 的取证。
    deltas = [g - t for t, g, _ in matched]
    abs_errs = [abs(d) for d in deltas]
    deltas_sorted = sorted(deltas)

    # 逐行平均误差
    line_sums = {}
    for gt_t, gen_t, gt_li in matched:
        bucket = line_sums.setdefault(gt_li, [])
        bucket.append(abs(gen_t - gt_t))
    line_errors_ms = [
        (sum(line_sums[i]) / len(line_sums[i])) if i in line_sums else None
        for i in range(len(gt_lines))
    ]

    def _pct(lst, q):
        if not lst:
            return 0.0
        idx = int(q * (len(lst) - 1))
        return lst[idx]

    def _mean(lst):
        return sum(lst) / len(lst) if lst else 0.0

    def _std(lst):
        if len(lst) < 2:
            return 0.0
        m = _mean(lst)
        return (sum((x - m) ** 2 for x in lst) / (len(lst) - 1)) ** 0.5

    tolerance = {
        "100ms": sum(1 for e in abs_errs if e < 100) / len(abs_errs),
        "250ms": sum(1 for e in abs_errs if e < 250) / len(abs_errs),
        "500ms": sum(1 for e in abs_errs if e < 500) / len(abs_errs),
    }

    return {
        "gt_chars": len(gt_chars),
        "matched_chars": len(matched),
        "coverage": len(matched) / len(gt_chars),
        "delta_ms": deltas,
        "abs_errors_ms": abs_errs,
        "line_errors_ms": line_errors_ms,
        "error_mean_ms": _mean(abs_errs),
        "error_median_ms": _pct(sorted(abs_errs), 0.5),
        "error_p90_ms": _pct(sorted(abs_errs), 0.9),
        "error_std_ms": _std(abs_errs),
        "bias_ms": _pct(deltas_sorted, 0.5),
        "tolerance": tolerance,
    }


def process_song(folder, model, device):
    """单首歌：对齐 + 评估，返回 (song_name, report_dict, generated_lrc)"""
    name = folder.name
    audio_path = folder / "audio.mp3"
    line_lrc_path = folder / "line.lrc"
    word_lrc_path = folder / "word.lrc"

    if (
        not audio_path.exists()
        or audio_path.stat().st_size < MIN_AUDIO_SIZE
        or not line_lrc_path.exists()
        or not word_lrc_path.exists()
    ):
        return name, {"status": "skipped", "reason": "缺少音频或歌词"}, None

    # 1. 解析逐行歌词（与 GUI 相同入口）
    parser = LrcParser()
    parser.parse(line_lrc_path.read_text(encoding="utf-8"), ".lrc")
    if not parser.lines_text:
        return name, {"status": "skipped", "reason": "line.lrc 无歌词行"}, None

    ref_text = "\n".join(parser.lines_text)
    spaced_ref_text = preprocess_cjk_spaces(ref_text)

    # 2. 结构化强制对齐（与 core/whisper_worker.run_inference_task 同款参数）
    result = model.align(
        str(audio_path),
        spaced_ref_text,
        language=LANGUAGE,
        suppress_silence=True,
        regroup=False,
    )

    # 3. 合成逐字 LRC
    aligner = LrcAligner(
        parser,
        time_offset=0.0,
        enable_force_calibration=True,
        enable_avg_distribution=False,
        calibration_threshold=1.5,
    )
    stop_event = Event()
    stop_event.clear()
    gen_lrc = aligner.run(result, stop_event, _ProgressSink())

    # 4. 保存生成结果
    gen_path = folder / "generated.lrc"
    gen_path.write_text(gen_lrc, encoding="utf-8")

    # 5. 与真值对比
    gt_content = word_lrc_path.read_text(encoding="utf-8")
    metrics = compare_gt_generated(gt_content, gen_lrc)

    report = {
        "status": "ok",
        "audio_size_mb": round(audio_path.stat().st_size / 1048576, 1),
        "line_count": len(parser.lines_text),
        "gen_chars": len(parse_word_lrc(gen_lrc)),
        **metrics,
    }
    return name, report, gen_lrc


def main():
    ap = argparse.ArgumentParser(description="REATK 逐字对齐自动化测试")
    ap.add_argument("--dir", default=os.path.join(PROJECT_ROOT, "testdata"))
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 首（0=全部）")
    ap.add_argument("--force", action="store_true", help="已有 generated.lrc 也重跑")
    ap.add_argument(
        "--compare-only",
        action="store_true",
        help="跳过模型加载/对齐，仅用已有 generated.lrc 重算对比指标（快速）",
    )
    ap.add_argument("--verbose", action="store_true", help="打印对齐器日志")
    args = ap.parse_args()

    data_dir = os.path.abspath(args.dir)
    if not os.path.isdir(data_dir):
        print(f"数据目录不存在: {data_dir}")
        sys.exit(1)

    folders = [
        Path(f.path)
        for f in sorted(os.scandir(data_dir), key=lambda e: e.name)
        if f.is_dir()
    ]
    if args.limit > 0:
        folders = folders[: args.limit]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.compare_only:
        print(f"对比模式：仅重算指标（不加载模型），{len(folders)} 首")
        model = None
    else:
        print(f"设备: {device.upper()} | 模型: small | 语言: {LANGUAGE}")
        t0 = time.time()
        model = stable_whisper.load_model(
            "small", download_root=os.path.join(PROJECT_ROOT, "models"), device=device
        )
        print(f"模型加载完成 ({time.time() - t0:.1f}s)")

    report = {
        "model": "small",
        "language": LANGUAGE,
        "device": device,
        "songs": [],
    }
    for fi, folder in enumerate(folders):
        name = folder.name
        gen_path = folder / "generated.lrc"
        if not os.path.exists(gen_path):
            if args.compare_only:
                print(f"[{fi + 1}/{len(folders)}] {name}: 跳过（无 generated.lrc）")
                continue
            if not args.force:
                print(f"[{fi + 1}/{len(folders)}] {name}: 跳过（已有 generated.lrc，--force 重跑）")
                continue

        t_start = time.time()
        try:
            if args.compare_only:
                # 仅对比：读取已有 generated.lrc 与真值 word.lrc
                word_lrc_path = folder / "word.lrc"
                gt_content = word_lrc_path.read_text(encoding="utf-8")
                gen_lrc = gen_path.read_text(encoding="utf-8")
                metrics = compare_gt_generated(gt_content, gen_lrc)
                audio_path = folder / "audio.mp3"
                song_report = {
                    "status": "ok",
                    "audio_size_mb": (
                        round(audio_path.stat().st_size / 1048576, 1)
                        if audio_path.exists()
                        else None
                    ),
                    "gen_chars": len(parse_word_lrc(gen_lrc)),
                    **metrics,
                }
            else:
                song_name, song_report, _ = process_song(folder, model, device)
                name = song_name
            report["songs"].append({"name": name, **song_report})
            st = song_report.get("status")
            if st == "ok":
                cov = song_report["coverage"]
                med = song_report["error_median_ms"]
                p90 = song_report["error_p90_ms"]
                bias = song_report["bias_ms"]
                tol = song_report["tolerance"]
                print(
                    f"[{fi + 1}/{len(folders)}] {name}:"
                    f" 覆盖 {cov:.1%} | 中位误差 {med:.0f}ms | P90 {p90:.0f}ms"
                    f" | 偏置 {bias:+.0f}ms | <100ms {tol['100ms']:.0%} <250ms {tol['250ms']:.0%}"
                    f" | {time.time() - t_start:.0f}s"
                )
            else:
                print(f"[{fi + 1}/{len(folders)}] {name}: {song_report.get('reason', st)}")
        except Exception as e:
            import traceback

            if args.verbose:
                traceback.print_exc()
            else:
                print(f"[{fi + 1}/{len(folders)}] {name}: 失败: {e}")
            report["songs"].append({"name": name, "status": "error", "error": str(e)})

    # 汇总报告
    report_path = os.path.join(data_dir, "test_report.json")
    # delta_ms 等大列表不写盘（报告只保留统计量）
    for s in report["songs"]:
        for k in ("delta_ms", "abs_errors_ms", "line_errors_ms"):
            s.pop(k, None)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入: {report_path}")

    # 汇总表
    ok = [s for s in report["songs"] if s.get("status") == "ok"]
    if ok:
        covs = [s["coverage"] for s in ok]
        meds = [s["error_median_ms"] for s in ok]
        p90s = [s["error_p90_ms"] for s in ok]
        biases = [s["bias_ms"] for s in ok]
        print("\n===== 整体汇总 =====")
        print(f"成功 {len(ok)}/{len(report['songs'])} 首")
        print(
            f"字符覆盖率    平均 {sum(covs) / len(covs):.1%}"
            f"  范围 {min(covs):.1%}~{max(covs):.1%}"
        )
        print(
            f"中位误差      平均 {sum(meds) / len(meds):.0f}ms"
            f"  范围 {min(meds):.0f}~{max(meds):.0f}ms"
        )
        print(
            f"P90 误差      平均 {sum(p90s) / len(p90s):.0f}ms"
            f"  范围 {min(p90s):.0f}~{max(p90s):.0f}ms"
        )
        print(
            f"全局偏置      平均 {sum(biases) / len(biases):+.0f}ms"
            f"  范围 {min(biases):+.0f}~{max(biases):+.0f}ms"
        )
        tol_keys = ("100ms", "250ms", "500ms")
        for k in tol_keys:
            vals = [s["tolerance"][k] for s in ok]
            print(f"容差 <{k}   平均 {sum(vals) / len(vals):.1%}")


if __name__ == "__main__":
    main()