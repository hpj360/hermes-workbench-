#!/usr/bin/env python3
"""
抖音视频内容提取器（完整能力版）

能力矩阵（2026-07-11 补齐 6 缺口后）：
1. 链接解析（iesdouyin SSR，无需 Cookie/Key）
2. 元数据（标题/作者/统计）
3. 无水印下载（playwm→play）
4. 语音转文字 + 时间轴 segments（openai-whisper）
5. 长视频完整转写（分段转写 + 时间轴偏移拼接）
6. 画面抽帧（ffmpeg 按间隔抽帧，供 VLM 理解）
7. 视频内嵌文字 OCR（rapidocr-onnxruntime）
8. LLM 校对接口（输出待校对文本 + 提示词模板，由调用方执行）

原理：iesdouyin.com/share/video/{id} 的 SSR 页面含 window._ROUTER_DATA JSON，
直接取 play_addr.url_list[0] 并把 playwm 替换为 play 即得无水印直链。
借鉴 yzfly/douyin-mcp-server v1.2.1 的解析逻辑（Apache 2.0）。

用法：
  python3 douyin_reader.py "<URL>" --json                        # 默认：解析+下载+转写(5分钟)
  python3 douyin_reader.py "<URL>" --full-transcribe --json      # 完整转写（分段拼接）
  python3 douyin_reader.py "<URL>" --extract-frames --ocr --json # 抽帧+OCR
  python3 douyin_reader.py "<URL>" --skip-transcribe --json      # 只解析+下载
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import requests


# 移动端 UA（iesdouyin 对 UA 不严格，但移动端更稳定）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
}


def run_cmd(cmd, timeout=300):
    """执行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "命令超时", 1
    except Exception as e:
        return "", str(e), 1


# ── Layer 1: SSR 解析 + 下载 ──────────────────────────────────────────

def resolve_share_url(share_text: str) -> dict:
    """解析抖音分享链接，返回无水印视频信息。

    核心逻辑（借鉴 yzfly/douyin-mcp-server，实测 2026-07-11 可用）：
    1. 正则提取分享文本中的 URL
    2. 跟随重定向拿到 video_id
    3. 请求 iesdouyin.com/share/video/{id} 分享页
    4. 正则抓 window._ROUTER_DATA 的 SSR JSON
    5. 取 play_addr.url_list[0]，playwm → play 去水印
    """
    urls = re.findall(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        share_text,
    )
    if not urls:
        raise ValueError("未找到有效的分享链接")

    share_url = urls[0]
    share_response = requests.get(share_url, headers=HEADERS, allow_redirects=True, timeout=30)
    video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]

    detail_url = f"https://www.iesdouyin.com/share/video/{video_id}"
    response = requests.get(detail_url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    pattern = re.compile(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>", re.DOTALL)
    find_res = pattern.search(response.text)
    if not find_res or not find_res.group(1):
        raise ValueError("从 HTML 中解析视频信息失败（_ROUTER_DATA 未匹配），可能抖音改版")

    try:
        json_data = json.loads(find_res.group(1).strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"抖音 SSR JSON 解析失败，可能页面结构已改版: {e}")
    VIDEO_KEY = "video_(id)/page"
    NOTE_KEY = "note_(id)/page"
    if VIDEO_KEY in json_data["loaderData"]:
        info = json_data["loaderData"][VIDEO_KEY]["videoInfoRes"]
    elif NOTE_KEY in json_data["loaderData"]:
        info = json_data["loaderData"][NOTE_KEY]["videoInfoRes"]
    else:
        raise Exception(f"无法从 JSON 中解析视频或图集信息，loaderData 键: {list(json_data['loaderData'].keys())}")

    data = info["item_list"][0]
    video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
    desc = data.get("desc", "").strip() or f"douyin_{video_id}"
    desc = re.sub(r'[\\/:*?"<>|]', "_", desc)

    author = data.get("author", {}).get("nickname", "")
    stats = data.get("statistics", {})
    # 视频时长（秒），用于判断是否需要分段转写
    duration = data.get("video", {}).get("duration", 0) / 1000  # ms → s

    return {
        "video_id": video_id,
        "title": desc,
        "download_url": video_url,
        "author": author,
        "like_count": stats.get("digg_count", 0),
        "comment_count": stats.get("comment_count", 0),
        "share_count": stats.get("share_count", 0),
        "duration": round(duration, 1),
    }


def download_video(video_url: str, output_dir: str, max_bytes: int = 600 * 1024 * 1024) -> str:
    """下载无水印视频，返回文件路径。max_bytes 默认 600MB。超限时清理部分文件。"""
    video_path = os.path.join(output_dir, "video.mp4")
    try:
        response = requests.get(video_url, headers=HEADERS, stream=True, allow_redirects=True, timeout=60)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if response.status_code != 200 or "video" not in content_type:
            raise Exception(f"下载失败：状态码 {response.status_code}，Content-Type {content_type}")

        total = 0
        with open(video_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        raise Exception(f"视频超过 {max_bytes // 1024 // 1024}MB 限制")
        return video_path
    except Exception:
        # 下载失败或超限时清理部分文件
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError:
                pass
        raise


# ── 能力4+5: 语音转写 + 时间轴 + 长视频分段 ───────────────────────────

def extract_audio(video_path: str, output_dir: str, start: float = 0, duration: float | None = None) -> str:
    """用 ffmpeg 抽音频（16kHz 单声道 WAV，whisper 推荐格式）。

    start/duration 用于分段转写：从 start 秒开始，抽取 duration 秒音频。
    """
    audio_path = os.path.join(output_dir, f"audio_{int(start)}.wav")
    cmd = ["ffmpeg", "-y", "-i", video_path]
    if start > 0:
        cmd += ["-ss", str(start)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path]

    stdout, stderr, code = run_cmd(cmd, timeout=300)
    if code != 0:
        raise Exception(f"ffmpeg 音频提取失败: {stderr}")
    return audio_path


def _transcribe_segment(audio_path: str, model, language: str) -> dict:
    """转写单个音频片段，返回 {text, segments}。"""
    initial_prompt = "以下是普通话的句子。" if language == "zh" else None
    result = model.transcribe(audio_path, language=language, verbose=False, initial_prompt=initial_prompt)

    timed_segments = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if text:
            timed_segments.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": text,
            })

    return {
        "text": result["text"],
        "segments": timed_segments,
    }


def transcribe_audio(audio_path: str, model_size: str = "small", language: str = "zh") -> dict:
    """转写单个音频文件，返回带时间轴 segments 的结果。

    实测（2026-07-11，沙箱 CPU）：
    - tiny (72MB)：3 分钟 10.5s，错字多，简繁混杂
    - small (461MB)：1 分钟 21.9s，语义清晰，专有名词需 LLM 校对
    - medium (1.5GB)：OOM Killed
    """
    try:
        import whisper
    except ImportError:
        return {"error": "openai-whisper 未安装，请运行: pip install openai-whisper"}

    try:
        model = whisper.load_model(model_size)
    except Exception as e:
        return {"error": f"模型加载失败: {e}"}

    try:
        seg_result = _transcribe_segment(audio_path, model, language)
        return {
            "full_text": seg_result["text"],
            "segments": seg_result["segments"],
            "language": language,
            "model": model_size,
        }
    except Exception as e:
        return {"error": f"语音转写失败: {e}"}


def transcribe_full(video_path: str, output_dir: str, total_duration: float,
                    model_size: str = "small", language: str = "zh",
                    segment_duration: float = 300) -> dict:
    """长视频完整转写：分段抽音频 → 逐段转写 → 时间轴偏移拼接。

    segment_duration 默认 300 秒（5 分钟）。118 分钟视频 ≈ 24 段。
    每段时间轴偏移 = 段索引 × segment_duration，拼接成完整时间轴。
    连续 3 段失败则熔断，避免视频损坏时浪费时间。
    """
    # duration=0 检查必须在 whisper import 之前，避免无谓依赖加载
    if total_duration <= 0:
        return {"error": "视频时长未知（duration=0），无法分段转写，请用 --max-duration 模式"}

    try:
        import whisper
    except ImportError:
        return {"error": "openai-whisper 未安装，请运行: pip install openai-whisper"}

    try:
        model = whisper.load_model(model_size)
    except Exception as e:
        return {"error": f"模型加载失败: {e}"}

    import math
    all_text = []
    all_segments = []
    failed_segments = []
    consecutive_failures = 0
    num_segments = math.ceil(total_duration / segment_duration) if total_duration > 0 else 0
    succeeded = 0

    for i in range(num_segments):
        start = i * segment_duration
        seg_dur = min(segment_duration, total_duration - start)
        print(f"    段 {i+1}/{num_segments}: {start:.0f}s-{start+seg_dur:.0f}s ...", flush=True)

        seg_audio = None
        seg_result = None
        try:
            seg_audio = extract_audio(video_path, output_dir, start=start, duration=seg_dur)
            seg_result = _transcribe_segment(seg_audio, model, language)
            consecutive_failures = 0
            succeeded += 1
        except Exception as e:
            print(f"    段 {i+1} 失败: {e}", flush=True)
            failed_segments.append({"index": i + 1, "start": start, "end": start + seg_dur, "error": str(e)})
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print(f"    连续 {consecutive_failures} 段失败，熔断停止", flush=True)
                break
        finally:
            # 无论成功失败都清理分段音频
            if seg_audio and os.path.exists(seg_audio):
                try:
                    os.remove(seg_audio)
                except OSError:
                    pass

        if seg_result and seg_result["text"]:
            all_text.append(seg_result["text"])
        # 时间轴偏移：每段的 start/end 加上该段在完整视频中的偏移量
        if seg_result:
            for seg in seg_result["segments"]:
                all_segments.append({
                    "start": round(seg["start"] + start, 2),
                    "end": round(seg["end"] + start, 2),
                    "text": seg["text"],
                })

    return {
        "full_text": "\n".join(all_text),
        "segments": all_segments,
        "language": language,
        "model": model_size,
        "segment_duration": segment_duration,
        "total_chunks": num_segments,
        "succeeded_chunks": succeeded,
        "failed_chunks": len(failed_segments),
        "failed_segments": failed_segments,
    }


# ── 能力6+7: 画面抽帧 + OCR ───────────────────────────────────────────

def extract_frames(video_path: str, output_dir: str, interval: int = 30) -> list[str]:
    """用 ffmpeg 按间隔抽帧，返回图片路径列表。

    interval 默认 30 秒（每 30 秒抽一帧）。教学视频 PPT 切换通常 >30s。
    抽帧分辨率压缩到宽度 640（OCR 不需要高分辨率，减小体积）。
    抽帧前清空 frames 目录，避免复用 output_dir 时旧帧污染。
    """
    import shutil
    frames_dir = os.path.join(output_dir, "frames")
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    frame_pattern = os.path.join(frames_dir, "frame_%05d.jpg")

    # -vf fps=1/interval：每 interval 秒一帧；scale=640:-1 宽度 640 保持比例
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"fps=1/{interval},scale=640:-1",
        "-q:v", "3",
        frame_pattern,
    ]
    stdout, stderr, code = run_cmd(cmd, timeout=600)
    if code != 0:
        raise Exception(f"ffmpeg 抽帧失败: {stderr}")

    frames = sorted([
        os.path.join(frames_dir, f) for f in os.listdir(frames_dir)
        if f.endswith(".jpg")
    ])
    return frames


def ocr_frames(frame_paths: list[str], interval: int = 30) -> list[dict]:
    """对帧列表做 OCR，提取内嵌文字。

    用 rapidocr-onnxruntime（CPU 友好，中英文识别）。
    interval 是抽帧间隔（秒），用于计算每帧的时间戳：timestamp = (frame_num - 1) * interval。
    返回每帧的 {frame, timestamp, texts} 列表。
    """
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return [{"error": "rapidocr-onnxruntime 未安装，请运行: pip install rapidocr-onnxruntime"}]

    try:
        ocr = RapidOCR()
    except Exception as e:
        return [{"error": f"OCR 引擎初始化失败: {e}"}]

    results = []
    for i, frame_path in enumerate(frame_paths):
        try:
            result, _ = ocr(frame_path)
            texts = []
            if result:
                for box, text, conf in result:
                    # rapidocr 返回的 conf 可能是 str，需转 float
                    try:
                        conf_val = float(conf)
                    except (TypeError, ValueError):
                        conf_val = 0.0
                    if text and conf_val > 0.5:  # 置信度过滤
                        texts.append(text)
            # 从文件名提取帧序号，估算时间戳（帧序号从1开始，第1帧=0秒）
            try:
                frame_num = int(os.path.basename(frame_path).split("_")[1].split(".")[0])
            except (IndexError, ValueError):
                frame_num = i + 1  # 文件名解析失败时用循环索引兜底
            results.append({
                "frame": frame_path,
                "frame_num": frame_num,
                "timestamp": round((frame_num - 1) * interval, 2),
                "texts": texts,
            })
        except Exception as e:
            results.append({"frame": frame_path, "error": str(e)})

    return results


# ── 能力8: LLM 校对接口 ───────────────────────────────────────────────

LLM_CORRECT_PROMPT = """请校对以下抖音视频转写文字，修正专有名词和明显错字，保持原意不变。

已知背景信息：
- 视频标题：{title}
- 作者：{author}
{ocr_context}
转写文字：
{text}

要求：
1. 修正专有名词（如技术名词、产品名、人名）的识别错误
2. 修正明显同音错字
3. 不改变原意，不增删内容
4. 输出校对后的纯文本，不加解释
"""


def build_llm_correct_prompt(text: str, title: str, author: str, ocr_terms: list[str] | None = None) -> str:
    """生成 LLM 校对提示词，由调用方（AI agent）执行。

    ocr_terms 是从画面 OCR 识别到的专有名词列表，作为校对参考（如 GStack、Agent 等）。
    """
    ocr_context = ""
    if ocr_terms:
        ocr_context = f"- 画面 OCR 识别到的专有名词参考：{', '.join(ocr_terms[:20])}\n"
    return LLM_CORRECT_PROMPT.format(title=title, author=author, ocr_context=ocr_context, text=text)


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="抖音视频内容提取器（完整能力版）")
    parser.add_argument("url", help="抖音视频链接或分享文本")
    parser.add_argument("--output-dir", help="输出目录（默认临时目录）")
    parser.add_argument("--model", default="small", help="Whisper 模型 (tiny/base/small/medium/large)，默认 small")
    parser.add_argument("--language", default="zh", help="音频语言 (zh/en/ja/ko 等)")
    parser.add_argument("--max-duration", type=int, default=300,
                        help="转写最大时长（秒），默认 300。与 --full-transcribe 互斥")
    parser.add_argument("--full-transcribe", action="store_true",
                        help="完整转写（分段拼接，忽略 max-duration）。长视频耗时较长")
    parser.add_argument("--segment-duration", type=int, default=300,
                        help="完整转写时分段长度（秒），默认 300")
    parser.add_argument("--extract-frames", action="store_true",
                        help="抽帧（供 VLM 画面理解），默认每 30 秒一帧")
    parser.add_argument("--frame-interval", type=int, default=30,
                        help="抽帧间隔（秒），默认 30")
    parser.add_argument("--ocr", action="store_true",
                        help="对抽出的帧做 OCR，提取内嵌文字（需 --extract-frames）")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过语音转写")
    parser.add_argument("--llm-correct-prompt", action="store_true",
                        help="输出 LLM 校对提示词（由调用方执行校对）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    # 参数校验
    if args.ocr and not args.extract_frames:
        parser.error("--ocr 需要 --extract-frames 同时启用")

    output_dir = args.output_dir or tempfile.mkdtemp(prefix="douyin_")
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: SSR 解析
    if not args.json:
        print(f"[1/4] SSR 解析分享链接...")
    try:
        info = resolve_share_url(args.url)
    except Exception as e:
        error_msg = f"解析失败: {e}"
        if args.json:
            print(json.dumps({"success": False, "error": error_msg}, ensure_ascii=False, indent=2))
        else:
            print(f"  {error_msg}")
        sys.exit(1)

    if not args.json:
        print(f"  标题: {info['title'][:60]}")
        print(f"  作者: {info['author']}")
        print(f"  时长: {info['duration']}s | 点赞: {info['like_count']} 评论: {info['comment_count']} 分享: {info['share_count']}")

    # Step 2: 下载视频
    if not args.json:
        print(f"[2/4] 下载无水印视频...")
    try:
        video_path = download_video(info["download_url"], output_dir)
        size_mb = os.path.getsize(video_path) / 1024 / 1024
        if not args.json:
            print(f"  下载完成: {size_mb:.1f}MB -> {video_path}")
    except Exception as e:
        error_msg = f"下载失败: {e}"
        if args.json:
            print(json.dumps({"success": False, "error": error_msg, **info}, ensure_ascii=False, indent=2))
        else:
            print(f"  {error_msg}")
        sys.exit(1)

    # Step 3: 语音转写
    transcription = None
    if not args.skip_transcribe:
        if args.full_transcribe:
            total_dur = info.get("duration", 0)
            if total_dur <= 0:
                transcription = {"error": "视频时长未知（duration=0），无法分段转写，请用 --max-duration 模式"}
                if not args.json:
                    print(f"  {transcription['error']}")
            else:
                import math
                num_seg = math.ceil(total_dur / args.segment_duration)
                if not args.json:
                    print(f"[3/4] 完整转写 (model={args.model}, {total_dur:.0f}s, {num_seg}段)...")
                transcription = transcribe_full(
                    video_path, output_dir, total_dur,
                    model_size=args.model, language=args.language,
                    segment_duration=args.segment_duration,
                )
        else:
            if not args.json:
                print(f"[3/4] 抽音频 + 转写 (model={args.model}, max_duration={args.max_duration}s)...")
            audio_path = None
            try:
                audio_path = extract_audio(video_path, output_dir, duration=args.max_duration)
                transcription = transcribe_audio(audio_path, model_size=args.model, language=args.language)
            except Exception as e:
                transcription = {"error": str(e)}
            finally:
                # 单段转写完成后清理音频文件
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except OSError:
                        pass

        if transcription and "error" in transcription:
            if not args.json:
                print(f"  转写失败: {transcription['error']}")
        elif transcription:
            if not args.json:
                seg_count = len(transcription.get("segments", []))
                print(f"  转写完成: {len(transcription['full_text'])} 字符, {seg_count} 段时间轴")

    # Step 4: 抽帧 + OCR
    frames = None
    ocr_results = None
    if args.extract_frames:
        if not args.json:
            print(f"[4/4] 抽帧 (interval={args.frame_interval}s)...")
        try:
            frames = extract_frames(video_path, output_dir, interval=args.frame_interval)
            if not args.json:
                print(f"  抽帧完成: {len(frames)} 帧 -> {output_dir}/frames/")

            if args.ocr:
                if not args.json:
                    print(f"  OCR 识别中...")
                ocr_results = ocr_frames(frames, interval=args.frame_interval)
                if not args.json:
                    valid = [r for r in ocr_results if r.get("texts")]
                    total_texts = sum(len(r.get("texts", [])) for r in ocr_results)
                    print(f"  OCR 完成: {len(valid)} 帧有文字, 共 {total_texts} 条文本")
        except Exception as e:
            if not args.json:
                print(f"  抽帧/OCR 失败: {e}")
            frames = None
            ocr_results = None

    # 生成 LLM 校对提示词（注入 OCR 专有名词作为校对参考）
    llm_prompt = None
    if args.llm_correct_prompt and transcription and "full_text" in transcription:
        ocr_terms = None
        if ocr_results:
            # 从 OCR 结果提取去重的专有名词候选
            all_texts = []
            for r in ocr_results:
                if r.get("texts"):
                    all_texts.extend(r["texts"])
            if all_texts:
                ocr_terms = list(dict.fromkeys(all_texts))  # 去重保序
        llm_prompt = build_llm_correct_prompt(
            transcription["full_text"], info["title"], info["author"], ocr_terms
        )

    # 输出结果
    result = {
        "success": True,
        "video_id": info["video_id"],
        "title": info["title"],
        "author": info["author"],
        "duration": info["duration"],
        "like_count": info["like_count"],
        "comment_count": info["comment_count"],
        "share_count": info["share_count"],
        "video_file": video_path,
        "transcription": transcription,
        "frames": frames,
        "ocr_results": ocr_results,
        "llm_correct_prompt": llm_prompt,
    }

    if args.json:
        output = {k: v for k, v in result.items() if k != "video_file"}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"标题: {result['title']}")
        print(f"作者: {result['author']}")
        print(f"时长: {result['duration']}s | 点赞: {result['like_count']} | 评论: {result['comment_count']} | 分享: {result['share_count']}")
        if transcription and "full_text" in transcription:
            print(f"\n--- 转写文字（{transcription['model']} 模型, {len(transcription.get('segments', []))} 段时间轴）---")
            print(transcription["full_text"][:500] + ("..." if len(transcription["full_text"]) > 500 else ""))
        if ocr_results:
            print(f"\n--- OCR 文字（{len(ocr_results)} 帧）---")
            for r in ocr_results[:3]:
                if r.get("texts"):
                    print(f"  [{r.get('timestamp', '?')}s] {' | '.join(r['texts'][:3])}")
            if len(ocr_results) > 3:
                print(f"  ... 共 {len(ocr_results)} 帧")
        if llm_prompt:
            print(f"\n--- LLM 校对提示词 ---")
            print(llm_prompt)
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
