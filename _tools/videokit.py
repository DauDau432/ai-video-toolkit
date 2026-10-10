"""Bộ công cụ dựng video: giọng thật -> timeline -> trộn âm -> render từng khung -> kiểm tra đồng bộ.

Chạy ở thư mục gốc dự án:
  python _tools/videokit.py timeline      # tính timeline theo giọng thật, in bảng để kiểm tra từ khóa
  python _tools/videokit.py still 12.5    # chụp 1 khung hình tại giây 12.5 (bản demo) để xem nhanh
  python _tools/videokit.py demo          # dựng bản demo (các cảnh trong demo_scenes) + báo cáo đồng bộ
  python _tools/videokit.py full          # dựng bản đầy đủ (cần docs/approval.md) + báo cáo đồng bộ
Thêm --workers N để đặt số tiến trình render. Định dạng timeline.json và HTML: xem _tools/README.md.
"""
import argparse
import base64
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.getcwd()
TIMELINE = os.path.join(ROOT, "docs", "timeline.json")
WORK = os.path.join(ROOT, "tmp", "videokit")
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_models", "faster-whisper-large-v3")
SR = 48000

TOL_PASS = 0.15   # Template mục 4.1: sự kiện chính lệch không quá ±150 ms
TOL_WARN = 0.30   # sai số nhận dạng của Whisper
MIN_CHANGED_PIXELS = 300  # ít hơn mức này coi như hình không thay đổi
VOICE_MAX_OCTAVE = 0.3  # đoạn giọng có cao độ lệch quá ~23% so với số đông là giọng khác
JOIN_MAX_PIXELS = 1000   # khung đầu mỗi đoạn render khác bản vẽ lại quá mức này là lỗi chỗ nối


def fail(msg):
    print(f"\n[LỖI] {msg}")
    sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def probe_duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=nw=1:nk=1", path])
    return float(out)


def file_hash(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()[:12]


# ---------------------------------------------------------------- Whisper

_whisper = None


def whisper():
    global _whisper
    if _whisper is None:
        try:
            import nvidia
            for d in glob.glob(os.path.join(list(nvidia.__path__)[0], "*", "bin")):
                os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
        except ImportError:
            pass
        from faster_whisper import WhisperModel
        if not os.path.exists(os.path.join(MODEL, "model.bin")):
            from huggingface_hub import snapshot_download
            print(f"Chưa có model Whisper, đang tải về {os.path.normpath(MODEL)} (2,9 GB, chỉ tải một lần)...")
            snapshot_download("Systran/faster-whisper-large-v3", local_dir=MODEL)
        try:
            _whisper = WhisperModel(MODEL, device="cuda", compute_type="float16")
        except Exception:
            _whisper = WhisperModel(MODEL, device="cpu", compute_type="int8")
    return _whisper


def transcribe(path):
    segs, _ = whisper().transcribe(path, language="vi", word_timestamps=True)
    return [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for s in segs for w in s.words]


def words_of(path):
    """Mốc thời gian từng từ của một file giọng, có cache theo nội dung file."""
    cache = os.path.join(WORK, "whisper", f"{os.path.basename(path)}-{file_hash(path)}.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    words = transcribe(path)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(words, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return words


def norm(s):
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def find_keyword(words, keyword, near=None, window=3.0):
    """Trả về (thời điểm bắt đầu từ khóa, độ giống). Khớp gần đúng, bỏ dấu."""
    kw = norm(keyword)
    tokens = [norm(w["w"]) for w in words]
    best = (0.0, None)
    for i in range(len(words)):
        if not tokens[i] or (near is not None and abs(words[i]["start"] - near) > window):
            continue
        s = ""
        for j in range(i, min(len(words), i + 15)):
            s += tokens[j]
            r = difflib.SequenceMatcher(None, kw, s).ratio()
            if r > best[0]:
                best = (r, words[i]["start"])
            if len(s) > len(kw) * 1.5:
                break
    return best[1], best[0]


# ---------------------------------------------------------------- Timeline

def load_source():
    if not os.path.exists(TIMELINE):
        fail("Không thấy docs/timeline.json")
    return json.load(open(TIMELINE, encoding="utf-8"))


def resolve(src, mode):
    """Đặt các đoạn giọng nối tiếp nhau theo thời lượng thật, rồi tính thời điểm của mọi action."""
    scenes = src["scenes"]
    if mode == "demo":
        ids = src.get("demo_scenes") or fail("timeline.json thiếu demo_scenes")
        scenes = [s for s in scenes if s["scene_id"] in ids]
    seg_gap = src.get("segment_gap", 0.3)
    scene_gap = src.get("scene_gap", 0.6)

    t = src.get("lead_in", 0.3)
    segments, out_scenes, errors = {}, [], []
    for sc in scenes:
        if not sc.get("segments"):
            errors.append(f"{sc['scene_id']}: thiếu danh sách 'segments'")
            continue
        sc_start = 0.0 if not out_scenes else out_scenes[-1]["end"]
        for k, item in enumerate(sc["segments"]):
            sid = item if isinstance(item, str) else item["id"]
            path = os.path.join(ROOT, "assets", "voice", f"{sid}.wav")
            if not os.path.exists(path):
                errors.append(f"{sid}: không thấy {os.path.relpath(path, ROOT)}")
                continue
            dur = probe_duration(path)
            segments[sid] = {"id": sid, "scene_id": sc["scene_id"], "file": path,
                             "start": round(t, 3), "end": round(t + dur, 3),
                             "words": [dict(w, start=round(w["start"] + t, 3), end=round(w["end"] + t, 3))
                                       for w in words_of(path)]}
            last = k == len(sc["segments"]) - 1
            gap = item.get("gap_after") if isinstance(item, dict) and "gap_after" in item else None
            t += dur + (gap if gap is not None else (sc.get("pause_after", scene_gap) if last else seg_gap))
        out_scenes.append({k: v for k, v in sc.items() if k not in ("actions",)} | {
            "start": round(sc_start, 3), "end": round(t, 3), "actions": []})

    total = round(t + src.get("tail", 0.5), 3)
    if out_scenes:
        out_scenes[-1]["end"] = total

    for sc, out in zip([s for s in scenes if s.get("segments")], out_scenes):
        for n, a in enumerate(sc.get("actions", [])):
            a = dict(a)
            a.setdefault("id", f"{sc['scene_id']}_a{n + 1}")
            anc = a.get("anchor") or {}
            seg = segments.get(anc.get("segment_id"))
            if not seg:
                errors.append(f"{a['id']}: anchor.segment_id '{anc.get('segment_id')}' không có trong cảnh đang dựng")
                continue
            base = seg["end"] if anc.get("at") == "end" else seg["start"]
            if anc.get("keyword"):
                hit, score = find_keyword(seg["words"], anc["keyword"])
                if score < 0.7:
                    heard = " ".join(w["w"] for w in seg["words"])
                    errors.append(f"{a['id']}: không tìm thấy từ khóa '{anc['keyword']}' trong {seg['id']}. "
                                  f"Whisper nghe được: \"{heard}\"")
                    continue
                base = hit
                a["keyword_time"] = hit
            a["start"] = round(base + anc.get("offset", 0.0), 3)
            a["end"] = round(a["start"] + a.get("duration", 0.0), 3)
            out["actions"].append(a)

    if errors:
        fail("Timeline có lỗi:\n  - " + "\n  - ".join(errors))

    return {
        "mode": mode,
        "width": src.get("width", 1920), "height": src.get("height", 1080), "fps": src.get("fps", 60),
        "duration": total,
        "scenes": out_scenes,
        "segments": {k: {kk: vv for kk, vv in v.items() if kk != "file"} for k, v in segments.items()},
        "actions": {a["id"]: a for s in out_scenes for a in s["actions"]},
        "_files": {k: v["file"] for k, v in segments.items()},
    }


def print_timeline(tl):
    print(f"\nTổng thời lượng: {tl['duration']:.2f}s, {tl['width']}x{tl['height']} @ {tl['fps']} fps")
    for sc in tl["scenes"]:
        print(f"\n[{sc['scene_id']}] {sc['start']:.2f}s - {sc['end']:.2f}s")
        for sid, seg in tl["segments"].items():
            if seg["scene_id"] == sc["scene_id"]:
                print(f"  {sid} {seg['start']:7.2f}-{seg['end']:7.2f}  {' '.join(w['w'] for w in seg['words'])}")
        for a in sc["actions"]:
            kw = a.get("anchor", {}).get("keyword", "")
            print(f"    -> {a['start']:7.2f}s {a.get('type', ''):12} {a['id']}  {kw}")


def save_resolved(tl):
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, f"timeline.{tl['mode']}.json")
    json.dump({k: v for k, v in tl.items() if k != "_files"}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return path


# ---------------------------------------------------------------- Âm thanh

def decode(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"])
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def pitch(path):
    """Cao độ trung vị (Hz) của giọng trong file: tự tương quan trên các khung có tiếng."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"])
    x = np.frombuffer(raw, dtype=np.float32)
    n, hop, lo, hi = 640, 320, 16000 // 400, 16000 // 60
    frames = [x[i:i + n] for i in range(0, len(x) - n, hop)]
    if not frames:
        return 0.0
    rms = np.array([np.sqrt(np.mean(f ** 2)) for f in frames])
    f0 = []
    for f in (f for f, r in zip(frames, rms) if r > np.percentile(rms, 50)):
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.5:
            f0.append(16000 / lag)
    return float(np.median(f0)) if f0 else 0.0


def check_voices(src):
    """Mọi đoạn giọng phải cùng một giọng đọc. Đoạn có cao độ lệch hẳn số đông (ví dụ nam lẫn nữ,
    file cũ sinh bằng giọng khác còn sót lại) là lỗi đầu vào."""
    ids = [i if isinstance(i, str) else i["id"] for sc in src["scenes"] for i in sc.get("segments", [])]
    f0 = {i: pitch(p) for i in ids if os.path.exists(p := os.path.join(ROOT, "assets", "voice", f"{i}.wav"))}
    good = [v for v in f0.values() if v > 0]
    if len(good) < 3:
        return
    med = float(np.median(good))
    bad = [f"{i} ({v:.0f} Hz)" for i, v in f0.items() if v > 0 and abs(np.log2(v / med)) > VOICE_MAX_OCTAVE]
    if bad:
        fail(f"Giọng đọc không đồng nhất: cao độ chung khoảng {med:.0f} Hz nhưng các đoạn sau lệch hẳn: {', '.join(bad)}. "
             "Có thể là file cũ sinh bằng giọng khác còn sót lại. Sinh lại các đoạn này bằng đúng giọng đã chọn rồi chạy lại.")
    print(f"Giọng đọc: {len(good)} đoạn, cao độ khoảng {med:.0f} Hz, đồng nhất.")


def place(buf, clip, at, gain=1.0):
    i = max(0, int(round(at * SR)))
    n = min(len(clip), len(buf) - i)
    if n > 0:
        buf[i:i + n] += clip[:n] * gain


def js_hash(s):
    h = 2166136261
    for c in s:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
    return h / 4294967295


def type_times(a):
    """Thời điểm hiện từng ký tự, cùng công thức với VK.typed trong vk.js, để tiếng gõ phím khớp chữ."""
    text = a["text"]
    dur = a.get("duration") or len(text) * 0.06
    acc, w = 0.0, []
    for i, c in enumerate(text):
        acc += 0.6 + 0.8 * js_hash(a["id"] + str(i)) + (0.6 if c == " " else 0)
        w.append(acc)
    return [a["start"] + v / acc * dur for v in w]


def mix(src, tl, out_path):
    n = int(round(tl["duration"] * SR))
    voice = np.zeros((n, 2), np.float32)
    for sid, seg in tl["segments"].items():
        place(voice, decode(tl["_files"][sid]), seg["start"], src.get("voice_volume", 1.0))

    total = voice.copy()
    for a in tl["actions"].values():
        if a.get("sfx"):
            clip = decode(os.path.join(ROOT, a["sfx"]))
            times = type_times(a) if a.get("type") == "type" and a.get("text") else [a["start"]]
            for at in times:
                place(total, clip, at + a.get("sfx_offset", 0.0), a.get("sfx_volume", 0.6))

    bgm = src.get("bgm")
    if bgm and bgm.get("file"):
        music = decode(os.path.join(ROOT, bgm["file"]))
        music = np.tile(music, (n // len(music) + 1, 1))[:n]
        # Giảm nhạc nền khi đang có lời (ducking), mượt trong khoảng 0,3 giây
        block = SR // 100
        rms = np.sqrt(np.mean(voice[: n // block * block].reshape(-1, block, 2) ** 2, axis=(1, 2)))
        active = np.convolve((rms > 0.01).astype(np.float32), np.ones(30), "same") > 0
        level = np.where(active, bgm.get("duck", 0.35), 1.0).astype(np.float32)
        level = np.convolve(level, np.ones(30) / 30, "same")
        env = np.repeat(level, block)
        env = np.pad(env, (0, n - len(env)), mode="edge")[:n]
        total += music * (env[:, None] * bgm.get("volume", 0.15))

    raw = os.path.join(WORK, f"mix_raw.{tl['mode']}.wav")
    run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-", raw],
        input=total.astype(np.float32).tobytes())
    # Chuẩn hóa âm lượng 2 lượt: khoảng -14 LUFS, đỉnh -1 dBTP (Template mục 10.4)
    m = subprocess.run(["ffmpeg", "-i", raw, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8").stderr
    j = json.loads(m[m.rindex("{"):m.rindex("}") + 1])
    af = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
          f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", af, "-ar", str(SR), "-ac", "2",
         "-t", f"{tl['duration']:.3f}", out_path])


# ---------------------------------------------------------------- Render

VK_JS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vk.js"), encoding="utf-8").read()
# Sau khi vẽ: ép trình duyệt tính bố cục rồi chờ font/ảnh vừa được dùng tải xong, tránh khung đầu mỗi tiến trình
# hiện font dự phòng rồi nhảy sang font thật (giật hình ở chỗ nối các đoạn).
RENDER_JS = ("async t => { await window.renderAtTime(t); window.VK.drawPointer(t); document.body.offsetHeight; "
             "await document.fonts.ready; await Promise.all([...document.images].filter(i => !i.complete)"
             ".map(i => i.decode().catch(() => {}))); }")
INIT_JS = """
window.__VIDEOKIT__ = true;
window.TIMELINE = __TIMELINE__;
window.requestAnimationFrame = function () { return 0; };
document.addEventListener('DOMContentLoaded', function () {
  var s = document.createElement('style');
  s.textContent = '*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}';
  document.head.appendChild(s);
});
"""


def encoder_args():
    test = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:r=60", "-frames:v", "5",
                           "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    if test.returncode == 0:
        return "h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "18",
                              "-b:v", "0", "-maxrate", "40M", "-bufsize", "80M", "-profile:v", "high"]
    return "libx264", ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-tune", "animation",
                       "-profile:v", "high", "-threads", "4"]


def open_page(p, html, tl_json, w, h):
    browser = p.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    page.add_init_script(INIT_JS.replace("__TIMELINE__", tl_json) + VK_JS)
    page.goto("file:///" + html.replace("\\", "/"))
    page.wait_for_load_state("networkidle")
    page.wait_for_function("typeof window.renderAtTime === 'function'", timeout=15000)
    page.evaluate("async () => { await Promise.all([...document.fonts].map(f => f.load().catch(() => {}))); await document.fonts.ready; }")
    return browser, page


def check_offline(src, tl):
    """Trang phải chạy không cần mạng: font, ảnh, script đều nằm trong dự án. Vẽ thử giữa mỗi cảnh
    (font chỉ tải khi được dùng) và chặn mọi yêu cầu ra mạng; có yêu cầu nào là lỗi đầu vào."""
    from playwright.sync_api import sync_playwright
    tl_json = json.dumps({k: v for k, v in tl.items() if k != "_files"}, ensure_ascii=False)
    urls = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": tl["width"], "height": tl["height"]})
        ctx.route(re.compile(r"^(?!file:|data:|blob:|about:)"), lambda r: (urls.append(r.request.url), r.abort()))
        page = ctx.new_page()
        page.add_init_script(INIT_JS.replace("__TIMELINE__", tl_json) + VK_JS)
        page.goto("file:///" + os.path.join(ROOT, src["html"]).replace("\\", "/"))
        page.wait_for_load_state("load")
        for sc in tl["scenes"]:
            page.evaluate(RENDER_JS, (sc["start"] + sc["end"]) / 2)
        browser.close()
    if urls:
        fail("HTML tải tài nguyên từ mạng (font, ảnh, script phải nằm trong assets/, xem _tools/README.md):\n  "
             + "\n  ".join(sorted(set(urls))))


def render_chunk(job):
    from playwright.sync_api import sync_playwright
    html, tl_json, w, h, fps, a, b, out, enc = job
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                           *enc, "-g", str(fps * 2), "-colorspace", "bt709", "-color_primaries", "bt709",
                           "-color_trc", "bt709", out], stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser, page = open_page(p, html, tl_json, w, h)
        cdp = page.context.new_cdp_session(page)
        for f in range(a, b):
            page.evaluate(RENDER_JS, f / fps)
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
            ff.stdin.write(base64.b64decode(shot["data"]))
        browser.close()
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg lỗi ở đoạn khung {a}-{b}")
    return b - a


def render_video(src, tl, out_path, workers):
    html = os.path.join(ROOT, src.get("html", ""))
    if not src.get("html") or not os.path.exists(html):
        fail("timeline.json thiếu 'html' hoặc file HTML không tồn tại")
    fps, w, h = tl["fps"], tl["width"], tl["height"]
    frames = int(round(tl["duration"] * fps))
    enc_name, enc = encoder_args()
    tl_json = json.dumps({k: v for k, v in tl.items() if k != "_files"}, ensure_ascii=False)
    chunk_dir = os.path.join(WORK, f"chunks_{tl['mode']}")
    shutil.rmtree(chunk_dir, ignore_errors=True)
    os.makedirs(chunk_dir)
    bounds = np.linspace(0, frames, workers + 1).astype(int)
    jobs = [(html, tl_json, w, h, fps, int(bounds[i]), int(bounds[i + 1]),
             os.path.join(chunk_dir, f"c{i:02d}.mp4"), enc) for i in range(workers) if bounds[i + 1] > bounds[i]]
    print(f"\nRender {frames} khung hình ({w}x{h} @ {fps} fps) bằng {len(jobs)} tiến trình, mã hóa {enc_name}...")
    t0 = time.time()
    with ProcessPoolExecutor(len(jobs)) as ex:
        done = 0
        for n in ex.map(render_chunk, jobs):
            done += n
            print(f"  {done}/{frames} khung ({time.time() - t0:.0f}s)")
    lst = os.path.join(chunk_dir, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.writelines(f"file '{j[7].replace(chr(92), '/')}'\n" for j in jobs)
    video = os.path.join(chunk_dir, "video.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])
    return video, enc_name, time.time() - t0, [j[5] for j in jobs[1:]]


def still(src, tl, t, out_path):
    from playwright.sync_api import sync_playwright
    html = os.path.join(ROOT, src["html"])
    tl_json = json.dumps({k: v for k, v in tl.items() if k != "_files"}, ensure_ascii=False)
    with sync_playwright() as p:
        browser, page = open_page(p, html, tl_json, tl["width"], tl["height"])
        page.evaluate(RENDER_JS, t)
        page.screenshot(path=out_path)
        browser.close()


# ---------------------------------------------------------------- Kiểm tra

def check_joins(src, tl, video_path, joins):
    """Mỗi tiến trình render bắt đầu bằng trang mới. Vẽ lại khung đầu mỗi đoạn trên một trang đã chạy sẵn
    khung liền trước rồi so với video: khác nhau là trang chưa sẵn sàng (font, ảnh) hoặc renderAtTime
    phụ thuộc trạng thái cũ -> giật hình ở chỗ nối."""
    from playwright.sync_api import sync_playwright
    from PIL import Image
    import io
    fps, w, h = tl["fps"], tl["width"], tl["height"]
    tl_json = json.dumps({k: v for k, v in tl.items() if k != "_files"}, ensure_ascii=False)
    res = []
    with sync_playwright() as p:
        browser, page = open_page(p, os.path.join(ROOT, src["html"]), tl_json, w, h)
        cdp = page.context.new_cdp_session(page)
        for b in joins:
            worst = 0
            for f in (b - 2, b - 1, b, b + 1):
                page.evaluate(RENDER_JS, f / fps)
                if f < b:
                    continue
                shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                ref = np.asarray(Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("L"), dtype=int)
                got = gray_frame(video_path, (f - 0.25) / fps, w, h).astype(int)
                worst = max(worst, int(np.count_nonzero(np.abs(ref - got) > 24)))
            res.append((b, worst))
        browser.close()
    return res


def gray_frame(video, t, w, h):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1",
                                   "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    return np.frombuffer(raw, np.uint8)[: w * h].reshape(h, w)


def save_pair(video, t0, t1, path, label):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    imgs = []
    for t in (t0, t1):
        raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1",
                                       "-vf", "scale=960:-2", "-f", "image2pipe", "-vcodec", "png", "-"])
        import io
        imgs.append(Image.open(io.BytesIO(raw)).convert("RGB"))
    W, H = imgs[0].size
    sheet = Image.new("RGB", (W * 2 + 10, H + 50), (20, 20, 20))
    sheet.paste(imgs[0], (0, 50))
    sheet.paste(imgs[1], (W + 10, 50))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(sheet).text((10, 12), label, fill=(255, 255, 255), font=font)
    sheet.save(path, quality=90)


def check(src, tl, video_path, report_path, frames_dir, enc_name, render_secs, joins=()):
    print("\nKiểm tra thành phẩm...")
    rows, ok = [], True
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", video_path]))
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = map(int, v["r_frame_rate"].split("/"))
    fps = num / den
    vdur, adur = float(v["duration"]), float(a["duration"]) if a else 0
    tech = [
        ("Độ phân giải", f"{v['width']}x{v['height']}", (v["width"], v["height"]) == (tl["width"], tl["height"])),
        ("Khung hình/giây", f"{fps:g}", abs(fps - tl["fps"]) < 0.01),
        ("Codec hình", f"{v['codec_name']} {v.get('pix_fmt')}", v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p"),
        ("Bitrate hình", f"{int(v.get('bit_rate', 0)) / 1e6:.1f} Mbps (mã hóa theo chất lượng, cảnh ít chuyển động thì bitrate thấp là bình thường)", True),
        ("Âm thanh", f"{a['codec_name']} {a['sample_rate']} Hz {a['channels']} kênh" if a else "KHÔNG CÓ",
         bool(a) and a["codec_name"] == "aac" and a["sample_rate"] == "48000"),
        ("Thời lượng hình / tiếng", f"{vdur:.3f}s / {adur:.3f}s", abs(vdur - adur) <= 1.5 / tl["fps"] + 0.03),
    ]
    loud = subprocess.run(["ffmpeg", "-i", video_path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8").stderr
    li = re.findall(r"I:\s+(-?[\d.]+) LUFS", loud)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", loud)
    if li:
        tech.append(("Âm lượng tổng", f"{li[-1]} LUFS, đỉnh {tp[-1] if tp else '?'} dBTP",
                     abs(float(li[-1]) + 14) <= 1.5 and (not tp or float(tp[-1]) <= -0.9)))
    if joins:
        bad = [f"{b / tl['fps']:.2f}s ({n:,} px)" for b, n in check_joins(src, tl, video_path, joins) if n > JOIN_MAX_PIXELS]
        tech.append(("Chỗ nối giữa các tiến trình render", "khung đầu mỗi đoạn khác khi vẽ lại: " + ", ".join(bad)
                     if bad else f"{len(joins)} chỗ nối, vẽ lại khớp video", not bad))
    ok &= all(t[2] for t in tech)

    # Nghe lại thành phẩm bằng Whisper, đo lại vị trí từ khóa trong video cuối
    heard = transcribe(video_path)
    os.makedirs(frames_dir, exist_ok=True)
    for f in glob.glob(os.path.join(frames_dir, "*.jpg")):
        os.remove(f)
    for n, act in enumerate(sorted(tl["actions"].values(), key=lambda x: x["start"]), 1):
        anc = act.get("anchor", {})
        status, delta_txt, kw_txt = "ĐẠT", "-", "-"
        if anc.get("keyword"):
            hit, score = find_keyword(heard, anc["keyword"], near=act["keyword_time"])
            if score < 0.7:
                status, kw_txt = "CẢNH BÁO", "không nghe thấy"
            else:
                expected = hit + anc.get("offset", 0.0)
                d = act["start"] - expected
                delta_txt, kw_txt = f"{d * 1000:+.0f} ms", f"{hit:.2f}s"
                status = "ĐẠT" if abs(d) <= TOL_PASS else "CẢNH BÁO" if abs(d) <= TOL_WARN else "KHÔNG ĐẠT"
        # Hai khung cách nhau tròn số giây để con trỏ nhấp nháy (VK.caret, chu kỳ 1 giây) cùng pha, không bị tính là thay đổi.
        # Click: chuột đã tới nơi trước lúc click và vòng sóng tắt sau 0,5 giây, nên chỉ còn kết quả của cú click.
        if act.get("type") in ("click", "double_click", "right_click"):
            before = act["start"] - 0.05
        else:
            before = act["start"] - 0.25
        after = before + max(1, int(np.ceil(act["end"] - before + 0.4)))
        changed = int(np.count_nonzero(np.abs(gray_frame(video_path, before, tl["width"], tl["height"]).astype(int)
                                              - gray_frame(video_path, after, tl["width"], tl["height"])) > 24))
        if changed < MIN_CHANGED_PIXELS and not act.get("no_visual_change"):
            status = "KHÔNG ĐẠT"
        if status == "KHÔNG ĐẠT":
            ok = False
        img = f"{n:02d}_{act['id']}.jpg"
        save_pair(video_path, before, after, os.path.join(frames_dir, img),
                  f"{act['id']} ({act.get('type', '')}) '{anc.get('keyword', '')}'  "
                  f"trước {before:.2f}s  |  sau {after:.2f}s  -  {status}")
        rows.append((act["id"], act.get("type", ""), anc.get("keyword", ""), kw_txt, f"{act['start']:.2f}s",
                     delta_txt, f"{changed:,} px", status, img))

    rel = os.path.relpath(frames_dir, os.path.dirname(report_path)).replace("\\", "/")
    L = [f"# Báo cáo đồng bộ ({tl['mode']})", "",
         f"Tạo tự động bởi `_tools/videokit.py` lúc {time.strftime('%Y-%m-%d %H:%M:%S')}. "
         "Mọi số liệu dưới đây là đo thật trên file video, không phải ước lượng.", "",
         f"**Kết quả chung: {'ĐẠT' if ok else 'KHÔNG ĐẠT'}**", "",
         f"File: `{os.path.relpath(video_path, ROOT)}` · mã hóa {enc_name} · render {render_secs:.0f} giây", "",
         "## Thông số kỹ thuật", "", "| Mục | Giá trị | Kết quả |", "|---|---|---|"]
    L += [f"| {k} | {val} | {'ĐẠT' if good else 'KHÔNG ĐẠT'} |" for k, val, good in tech]
    L += ["", "## Đồng bộ hình và tiếng", "",
          f"Từ khóa được Whisper nghe lại trong video cuối. Lệch = thời điểm hành động trừ thời điểm dự kiến "
          f"(từ khóa + offset); đạt nếu trong ±{TOL_PASS * 1000:.0f} ms. "
          f"\"Thay đổi\" = số điểm ảnh khác nhau giữa ngay trước và ngay sau hành động (click: không tính con trỏ và vòng sóng); "
          f"dưới {MIN_CHANGED_PIXELS} điểm ảnh coi như hình không đổi (hành động không hiện ra).", "",
          "| Hành động | Loại | Từ khóa | Nghe thấy lúc | Hành động lúc | Lệch | Thay đổi | Kết quả | Ảnh trước/sau |",
          "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | [xem]({rel}/{r[8]}) |" for r in rows]
    open(report_path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"Báo cáo: {os.path.relpath(report_path, ROOT)}  ->  {'ĐẠT' if ok else 'KHÔNG ĐẠT'}")
    return ok


# ---------------------------------------------------------------- Main

def build(mode, workers):
    src = load_source()
    if mode == "full" and not os.path.exists(os.path.join(ROOT, "docs", "approval.md")):
        fail("Bản demo chưa được duyệt (chưa có docs/approval.md). Không dựng bản đầy đủ.")
    os.makedirs(WORK, exist_ok=True)
    check_voices(src)
    tl = resolve(src, mode)
    print_timeline(tl)
    save_resolved(tl)
    check_offline(src, tl)

    audio = os.path.join(WORK, f"mix.{mode}.wav")
    print("\nTrộn âm thanh...")
    mix(src, tl, audio)
    video, enc_name, secs, joins = render_video(src, tl, None, workers)

    if mode == "demo":
        out = os.path.join(ROOT, "output", "preview", "demo.mp4")
        report = os.path.join(ROOT, "output", "preview", "sync-report.md")
        frames_dir = os.path.join(ROOT, "output", "preview", "sync-frames")
    else:
        name = re.sub(r"[^a-z0-9]+", "-", norm_name(src.get("project_name", "video"))).strip("-")
        ratio = "16x9" if tl["width"] > tl["height"] else "9x16" if tl["width"] < tl["height"] else "1x1"
        out = os.path.join(ROOT, "output", "final", f"{name}-{ratio}.mp4")
        report = os.path.join(ROOT, "output", "preview", "sync-report-full.md")
        frames_dir = os.path.join(ROOT, "output", "preview", "sync-frames-full")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2", "-movflags", "+faststart",
         "-t", f"{int(round(tl['duration'] * tl['fps'])) / tl['fps']:.4f}", out])
    print(f"\nĐã xuất: {os.path.relpath(out, ROOT)}")
    good = check(src, tl, out, report, frames_dir, enc_name, secs, joins)
    sys.exit(0 if good else 2)


def norm_name(s):
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["timeline", "still", "demo", "full"])
    ap.add_argument("time", nargs="?", type=float, help="giây cần chụp (lệnh still)")
    ap.add_argument("--full", action="store_true", help="lệnh timeline/still dùng toàn bộ cảnh thay vì demo")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    args = ap.parse_args()

    if args.command in ("demo", "full"):
        build(args.command, args.workers)
    src = load_source()
    tl = resolve(src, "full" if args.full else "demo")
    if args.command == "timeline":
        print_timeline(tl)
        print(f"\nĐã ghi: {os.path.relpath(save_resolved(tl), ROOT)}")
    else:
        if args.time is None:
            fail("Cần số giây, ví dụ: python _tools/videokit.py still 12.5")
        out = os.path.join(ROOT, "tmp", f"still_{args.time:.2f}.png")
        still(src, tl, args.time, out)
        print(f"Đã lưu: {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
