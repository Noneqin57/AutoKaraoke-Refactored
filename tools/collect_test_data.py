# -*- coding: utf-8 -*-
"""AutoKaraoke 测试数据采集脚本。

从 QQ音乐（歌词来源，方法学自 LDDC：https://github.com/chenmozhijin/LDDC）
搜索歌曲，下载：
  - 音乐文件（QQ音乐 M500 128k mp3 为主，网易云 320k 兜底）
  - 逐行歌词 line.lrc（行级时间戳 LRC）
  - 逐字歌词 word.lrc（每字内联 [mm:ss.mmm] 标签，与项目 lrc_aligner_v2 输出格式一致）

输出目录结构（默认 testdata/）：
  testdata/{歌手} - {歌名}/
      audio.mp3      # 音频
      line.lrc       # 逐行歌词（可作为项目输入）
      word.lrc       # 逐字歌词（真值，可直接与项目输出对比）
      meta.json      # 歌曲元信息 + 下载来源

用法：
  python tools/collect_test_data.py "周杰伦 晴天" "陈奕迅 孤勇者"
  python tools/collect_test_data.py --list 歌曲列表.txt --dir testdata
  python tools/collect_test_data.py "一首歌" --lyrics-only --force

依赖：仅 requests（系统 Python 即可，无需 .venv 的 torch/PyQt6）。
"""
import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests

# 项目根目录（脚本位于 tools/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 引入 QRC 解密（GPL-3.0，源自 LDDC，见 qrcrypto.py 头部说明）
from tools.qrcrypto import qrc_decrypt  # noqa: E402

# ---------------------------------------------------------------- 通用工具

# 音频魔数：mp3 ID3v2 / 帧同步、m4a ftyp
_MP3_MAGICS = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3")
_M4A_MAGICS = (b"\x00\x00\x00\x18ftyp", b"ftyp")


def _fmt_ms(ms: int) -> str:
    """毫秒 -> mm:ss.mmm（四舍五入进位，与 utils/time_utils.format_time 一致）。"""
    total_ms = max(0, int(round(ms)))
    minutes, remainder = divmod(total_ms, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _sanitize(name: str) -> str:
    """清洗文件名/文件夹名中的非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip()
    return name[:80] or "untitled"


def _download(url: str, dest: Path, timeout: int = 60) -> bool:
    """流式下载文件，验证音频魔数与最小体积。"""
    try:
        with requests.get(url, timeout=timeout, stream=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as r:
            r.raise_for_status()
            total = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        return False

    if total < 200 * 1024:  # 小于 200KB 视为错误页/试听碎片
        dest.unlink(missing_ok=True)
        return False
    with open(dest, "rb") as f:
        head = f.read(16)
    if not (head.startswith(_MP3_MAGICS) or head.startswith(_M4A_MAGICS)):
        dest.unlink(missing_ok=True)
        return False
    return True


# ---------------------------------------------------------------- QQ音乐 API

_QM_HEADERS = {
    "cookie": "tmeLoginType=-1;",
    "content-type": "application/json",
    "accept-encoding": "gzip",
    "user-agent": "okhttp/3.14.9",
}
_QM_COMM = {
    "ct": 11, "cv": "1003006", "v": "1003006", "os_ver": "15",
    "phonetype": "24122RKC7C", "tmeAppID": "qqmusiclight",
    "nettype": "NETWORK_WIFI", "udid": "0",
}


def _qm_musicu(method: str, module: str, param: dict, retries: int = 2) -> dict:
    """调用 QQ音乐 musicu.fcg 接口（结构学自 LDDC core/api/lyrics/qm.py）。"""
    data = json.dumps(
        {"comm": _QM_COMM, "request": {"method": method, "module": module, "param": param}},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    for attempt in range(retries + 1):
        try:
            r = requests.post("https://u.y.qq.com/cgi-bin/musicu.fcg",
                              data=data, headers=_QM_HEADERS, timeout=20)
            r.raise_for_status()
            d = r.json()
            if d.get("code") == 0 and d["request"]["code"] == 0:
                return d["request"]["data"]
            raise RuntimeError(f"QM API code={d.get('code')}")
        except Exception as e:
            if attempt == retries:
                raise RuntimeError(f"QM 请求失败({method}): {e}") from e
            time.sleep(1)


def qm_search(keyword: str, limit: int = 5) -> list[dict]:
    """搜索歌曲，返回标准化歌曲信息列表。"""
    param = {
        "search_id": str(random.randint(1, 20) * 18014398509481984
                         + random.randint(0, 4194304) * 4294967296
                         + round(time.time() * 1000) % 86400000),
        "remoteplace": "search.android.keyboard", "query": keyword,
        "search_type": 0, "num_per_page": limit, "page_num": 1,
        "highlight": 0, "nqc_flag": 0, "page_id": 1, "grp": 1,
    }
    data = _qm_musicu("DoSearchForQQMusicLite", "music.search.SearchCgiService", param)
    songs = []
    for s in data.get("body", {}).get("item_song", []):
        artists = " / ".join(x.get("name", "") for x in s.get("singer", []) if x.get("name"))
        songs.append({
            "id": str(s["id"]), "mid": s["mid"],
            "title": s.get("title", ""), "artist": artists,
            "album": s.get("album", {}).get("name", ""),
            "duration": s.get("interval", 0),  # 秒
        })
    return songs


def qm_get_lyrics_raw(song: dict) -> tuple[str, str]:
    """获取歌曲原始歌词。

    Returns:
        (解密后的歌词文本, 类型) 类型: "qrc"(逐字) / "lrc"(仅逐行) / "text"
    """
    from base64 import b64encode
    param = {
        "albumName": b64encode(song["album"].encode()).decode(),
        "crypt": 1, "ct": 19, "cv": 2111,
        "interval": song["duration"], "lrc_t": 0, "qrc": 1, "qrc_t": 0,
        "roma": 1, "roma_t": 0,
        "singerName": b64encode(song["artist"].encode()).decode() if song["artist"] else b64encode(b"").decode(),
        "songID": int(song["id"]), "songName": b64encode(song["title"].encode()).decode(),
        "trans": 1, "trans_t": 0, "type": 0,
    }
    res = _qm_musicu("GetPlayLyricInfo", "music.musichallSong.PlayLyricInfo", param)
    lyric_hex = res.get("lyric", "")
    qrc_t = res.get("qrc_t", 0) or res.get("lrc_t", 0)
    if not lyric_hex:
        raise RuntimeError("歌词为空")
    text = qrc_decrypt(lyric_hex)
    if "<Lyric_1" in text and "LyricContent=" in text:
        return text, "qrc"
    if re.search(r"\[\d+:\d+", text):
        return text, "lrc"
    return text, "text"


def qm_get_audio_url(song: dict) -> str:
    """获取 QQ音乐免费 128k mp3 下载地址（M500），VIP 歌曲返回空串。"""
    filename = f"M500{song['mid']}.mp3"
    guid = str(int(time.time() * 1000) % 10000000000)
    param = {"guid": guid, "songmid": [song["mid"]], "songtype": [0], "uin": "0",
             "loginflag": 1, "platform": "20", "filename": [filename]}
    data = _qm_musicu("CgiGetVkey", "vkey.GetVkeyServer", param)
    purl = (data.get("midurlinfo") or [{}])[0].get("purl") or ""
    if not purl:
        return ""
    return "https://dl.stream.qqmusic.qq.com/" + purl


# ---------------------------------------------------------------- 网易云兜底

_NE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://music.163.com/",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def ne_search(keyword: str, limit: int = 5) -> list[dict]:
    """网易云搜索歌曲（兜底用）。"""
    r = requests.get("https://music.163.com/api/search/get/web",
                     params={"csrf_token": "", "hlpretag": "", "hlposttag": "",
                             "s": keyword, "type": 1, "offset": 0,
                             "total": True, "limit": limit},
                     headers=_NE_HEADERS, timeout=20)
    r.raise_for_status()
    songs = []
    for s in r.json().get("result", {}).get("songs", []):
        songs.append({
            "id": str(s["id"]), "title": s.get("name", ""),
            "artist": " / ".join(a.get("name", "") for a in s.get("artists", [])),
            "album": (s.get("album") or {}).get("name", ""),
            "duration": (s.get("duration") or 0) // 1000,
        })
    return songs


def ne_get_audio_url(song_id: str) -> str:
    """网易云匿名获取 320k 播放地址，VIP 歌曲返回空串。"""
    r = requests.get(f"https://music.163.com/api/song/enhance/player/url?ids=[{song_id}]&br=320000",
                     headers=_NE_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json().get("data") or [{}]
    return (data[0] or {}).get("url") or ""


def _loose_title_match(ns_title: str, qq_title: str) -> bool:
    """松散标题匹配：去掉 (Live)/(DJ版)/[伴奏] 等括号后缀后比较。"""
    a = re.sub(r"[\(\[（【].*?[\)\]）】]", "", _norm(ns_title))
    b = re.sub(r"[\(\[（【].*?[\)\]）】]", "", _norm(qq_title))
    return bool(a) and a == b


def ne_find_audio(song: dict) -> tuple[str, str]:
    """网易云兜底：搜索并返回 (播放URL, 网易云歌曲id)。

    遍历候选（优先标题/歌手匹配者），找到第一个可播放的 URL。
    全部不可用返回 ("", "")。
    """
    ne_songs = ne_search(f"{song['title']} {song['artist']}")
    qq_artist = _norm(song["artist"].split("/")[0])

    def rank(ns):
        score = 0
        if _loose_title_match(ns["title"], song["title"]):
            score += 2
        if qq_artist and qq_artist in _norm(ns["artist"]):
            score += 1
        return score

    ne_songs.sort(key=rank, reverse=True)
    for ns in ne_songs:
        try:
            url = ne_get_audio_url(ns["id"])
        except Exception:
            continue
        if url:
            return url, ns["id"]
    return "", ""


# ---------------------------------------------------------------- QRC 解析

_QRC_XML_RE = re.compile(r'<Lyric_1 LyricType="1" LyricContent="(?P<content>.*?)"/>', re.DOTALL)
_QRC_LINE_RE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_QRC_WORD_RE = re.compile(r"((?:(?!\(\d+,\d+\)).)*)\((\d+),(\d+)\)")
_TAG_RE = re.compile(r"^\[(\w+):([^\]]*)\]$")


def parse_qrc(qrc_xml: str) -> tuple[dict, list]:
    """解析 QRC XML -> (标签 dict, 歌词行列表)。

    每行: {"start": ms, "end": ms, "words": [(text, start_ms, end_ms), ...]}
    （与 LDDC core/parser/qrc.py 的解析逻辑一致）
    """
    m = _QRC_XML_RE.search(qrc_xml)
    if not m:
        raise ValueError("不是合法的 QRC 格式")
    tags: dict[str, str] = {}
    lines = []
    for raw in m.group("content").splitlines():
        line = raw.strip()
        lm = _QRC_LINE_RE.match(line)
        if lm:
            start, duration, content = lm.groups()
            start = int(start)
            line_end = start + int(duration)
            words = []
            for wm in _QRC_WORD_RE.finditer(content):
                text, w_start, w_dur = wm.group(1), int(wm.group(2)), int(wm.group(3))
                words.append((text, w_start, w_start + w_dur))
            lines.append({"start": start, "end": line_end, "words": words})
            continue
        tm = _TAG_RE.match(line)
        if tm:
            tags[tm.group(1)] = tm.group(2)
    return tags, lines


def parse_lrc_text(text: str) -> tuple[dict, list]:
    """解析纯 LRC 文本 -> (标签, 行列表[无逐字 words])。"""
    tags: dict[str, str] = {}
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tm = _TAG_RE.match(line)
        if tm:
            tags[tm.group(1)] = tm.group(2)
            continue
        parts = re.findall(r"\[(\d+):(\d+[.:]\d+)\](.*)", line)
        for mnt, sec, content in parts:
            try:
                mnt_i, sec_f = int(mnt), float(sec.replace(":", "."))
                start = int((mnt_i * 60 + sec_f) * 1000)
            except ValueError:
                continue
            lines.append({"start": start, "end": start, "words": [(content, start, start)]})
    return tags, lines


# ---------------------------------------------------------------- LRC 生成

def to_line_lrc(tags: dict, lines: list) -> str:
    """逐行 LRC：`[mm:ss.mmm]整行文本`。"""
    out = []
    for k, v in [("ti", tags.get("ti")), ("ar", tags.get("ar")),
                 ("al", tags.get("al")), ("by", tags.get("by"))]:
        if v:
            out.append(f"[{k}:{v}]")
    if out:
        out.append("")
    for ln in lines:
        text = "".join(w[0] for w in ln["words"] if w[0])
        if not text.strip():
            continue  # 纯间奏行跳过
        out.append(f"[{_fmt_ms(ln['start'])}]{text}")
    return "\n".join(out)


def to_word_lrc(tags: dict, lines: list) -> str:
    """逐字 LRC：行首 `[mm:ss.mmm]` + 每字内联 `[mm:ss.mmm]字`。

    格式与 core/lrc_aligner_v2.py 的 _construct_line_string 输出一致，
    便于与程序生成结果直接 diff。
    """
    out = []
    for k, v in [("ti", tags.get("ti")), ("ar", tags.get("ar")),
                 ("al", tags.get("al")), ("by", tags.get("by"))]:
        if v:
            out.append(f"[{k}:{v}]")
    if out:
        out.append("")
    for ln in lines:
        words = [w for w in ln["words"] if w[0]]
        if not words:
            continue
        # 行时间戳 = 第一个字的开始时间（与项目输出一致）
        line_str = f"[{_fmt_ms(words[0][1])}]{words[0][0]}"
        for w_text, w_start, _ in words[1:]:
            line_str += f"[{_fmt_ms(w_start)}]{w_text}"
        out.append(line_str)
    return "\n".join(out)


# ---------------------------------------------------------------- 主流程

def process_keyword(keyword: str, out_dir: Path, max_songs: int,
                    lyrics_only: bool, force: bool, dedupe: set) -> dict:
    """处理一个关键词，返回统计信息。"""
    stats = {"keyword": keyword, "ok": 0, "skipped": 0, "failed": []}
    print(f"\n=== 搜索: {keyword} ===")
    try:
        songs = qm_search(keyword, limit=max(5, max_songs))
    except Exception as e:
        print(f"  搜索失败: {e}")
        stats["failed"].append("搜索失败")
        return stats
    if not songs:
        print("  无结果")
        stats["failed"].append("无结果")
        return stats

    for song in songs[:max_songs]:
        if song["mid"] in dedupe:
            print(f"  跳过重复: {song['title']} - {song['artist']}")
            stats["skipped"] += 1
            continue
        dedupe.add(song["mid"])

        folder = out_dir / f"{_sanitize(song['artist'])} - {_sanitize(song['title'])}"
        if folder.exists() and not force:
            print(f"  已存在，跳过: {folder.name}")
            stats["skipped"] += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)

        print(f"  [{song['title']} - {song['artist']}] ({song['duration']}s)")
        meta = {
            "title": song["title"], "artist": song["artist"], "album": song["album"],
            "duration_s": song["duration"], "qq_id": song["id"], "qq_mid": song["mid"],
            "lyric_type": None, "audio_source": None, "audio_url": None,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # ---- 1. 歌词 ----
        try:
            lyric_text, ltype = qm_get_lyrics_raw(song)
            if ltype == "qrc":
                tags, lines = parse_qrc(lyric_text)
            elif ltype == "lrc":
                tags, lines = parse_lrc_text(lyric_text)
            else:
                tags, lines = {}, []
                lines = [{"start": 0, "end": 0,
                          "words": [(t, 0, 0)]} for t in lyric_text.splitlines() if t.strip()]
            if not lines:
                raise RuntimeError("歌词解析为空")
            meta["lyric_type"] = ltype
            (folder / "line.lrc").write_text(to_line_lrc(tags, lines), encoding="utf-8")
            (folder / "word.lrc").write_text(to_word_lrc(tags, lines), encoding="utf-8")
            n_words = sum(len(ln["words"]) for ln in lines)
            print(f"    歌词: {ltype}, {len(lines)} 行, {n_words} 字")
        except Exception as e:
            print(f"    歌词获取失败: {e}")
            stats["failed"].append(f"{song['title']}: 歌词失败 {e}")
            (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
            continue

        # ---- 2. 音频 ----
        if not lyrics_only:
            url = ""
            try:
                url = qm_get_audio_url(song)
                if url and _download(url, folder / "audio.mp3"):
                    meta["audio_source"], meta["audio_url"] = "qqmusic", url
                    print(f"    音频: QQ音乐 128k OK")
            except Exception:
                url = ""
            if not meta["audio_source"]:
                # 网易云兜底（遍历候选直到拿到可播放 URL）
                try:
                    ne_url, ne_id = ne_find_audio(song)
                    if ne_url and _download(ne_url, folder / "audio.mp3"):
                        meta["audio_source"], meta["audio_url"] = "netease", ne_url
                        meta["netease_id"] = ne_id
                        print(f"    音频: 网易云 320k OK")
                except Exception as e:
                    print(f"    网易云兜底失败: {e}")
            if not meta["audio_source"]:
                print("    音频下载失败（VIP 或地区限制），仅保留歌词")
                stats["failed"].append(f"{song['title']}: 音频不可用")
                stats["ok"] += 1  # 歌词成功也算部分成功
                (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
                continue

        stats["ok"] += 1
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
        print(f"    => {folder.name}/ 完成")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AutoKaraoke 测试数据采集：音乐 + 逐行/逐字歌词",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("keywords", nargs="*", help="搜索关键词，例如：'周杰伦 晴天'")
    parser.add_argument("--list", dest="list_file", metavar="FILE",
                        help="关键词列表文件（每行一个）")
    parser.add_argument("--dir", default="testdata", help="输出目录（默认 testdata）")
    parser.add_argument("--max", type=int, default=1, help="每个关键词最多下载几首（默认 1）")
    parser.add_argument("--lyrics-only", action="store_true", help="只下载歌词，不下载音频")
    parser.add_argument("--force", action="store_true", help="强制重新下载已存在的歌曲")
    args = parser.parse_args()

    keywords = list(args.keywords)
    if args.list_file:
        lp = Path(args.list_file)
        if not lp.exists():
            print(f"列表文件不存在: {lp}", file=sys.stderr)
            sys.exit(1)
        keywords += [ln.strip() for ln in lp.read_text(encoding="utf-8").splitlines()
                     if ln.strip() and not ln.startswith("#")]

    if not keywords:
        parser.print_help()
        sys.exit(1)

    out_dir = Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录: {out_dir.resolve()}")
    t0 = time.time()
    dedupe: set = set()
    total = {"ok": 0, "skipped": 0, "failed": 0}
    for kw in keywords:
        st = process_keyword(kw, out_dir, args.max, args.lyrics_only, args.force, dedupe)
        total["ok"] += st["ok"]
        total["skipped"] += st["skipped"]
        total["failed"] += len(st["failed"])
        for f in st["failed"]:
            print(f"  [失败] {f}")

    print(f"\n=== 完成: 成功 {total['ok']}, 跳过 {total['skipped']}, 失败 {total['failed']} "
          f"(耗时 {time.time() - t0:.1f}s) ===")
    print(f"输出目录: {out_dir.resolve()}")


if __name__ == "__main__":
    main()