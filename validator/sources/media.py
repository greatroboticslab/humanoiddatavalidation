"""Video files: download (low resolution, no audio), cut frames inside every subtask's time range, draw contact
sheets, report disk usage and delete. Downloads are untrusted data: they stay in work/videos and are only read by ffmpeg."""
import glob, json, math, os, re, shutil, subprocess, textwrap, threading
import imageio_ffmpeg
import yt_dlp
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .. import config
from . import youtube

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VERSION = 2              # bump when the sampling scheme changes; older frame sets are re-extracted
SECONDS_PER_FRAME = 5    # one frame every ~5 s inside a subtask's range ...
MIN_FRAMES, MAX_FRAMES = 4, 12   # ... but never fewer than 4 or more than 12
OVERVIEW_FRAMES = 16
TILE = {"wide": (200, 112), "tall": (120, 213)}
# slow or flaky connections: retry downloads instead of failing the whole video
NET_RETRY = {"retries": 10, "fragment_retries": 10, "extractor_retries": 5, "socket_timeout": 60}
COLS = 6
_lock = threading.Lock()  # one download/extraction at a time


def fmt(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def finished_file(folder, vid):
    """The finished download for a video, ignoring unfinished pieces: '.part'/'.ytdl' files and the separate
    'id.f397.mp4' / 'id.f251.webm' streams yt-dlp keeps while joining picture and sound."""
    hits = [p for p in glob.glob(os.path.join(folder, vid + ".*"))
            if not p.endswith((".part", ".ytdl", ".temp")) and not re.match(re.escape(vid) + r"\.f\d+\.", os.path.basename(p))]
    return hits[0] if hits else None


def video_path(vid):
    return finished_file(config.VIDEO_DIR, vid)


def frame_dir(vid):
    return os.path.join(config.FRAME_DIR, vid)


def info(vid):
    try:
        with open(os.path.join(frame_dir(vid), "info.json"), encoding="utf-8") as f:
            i = json.load(f)
        return i if i.get("version") == VERSION else None
    except Exception:
        return None


def download(vid):
    p = video_path(vid)
    if p:
        return p
    # reuse the YouTube info request validation made a moment ago instead of asking YouTube a second time
    info = youtube.take_fresh_info(vid) or youtube.fetch_info(vid)
    opts = youtube.ydl_options(
        **NET_RETRY,
        # one file with picture AND sound: <=360p video + the audio stream, joined into one mp4 by ffmpeg.
        # The frames come from the picture, the transcript (speech.py) from the sound of the same file.
        format="bv*[height<=360]+ba/b[height<=360]/bv*[height<=360]/w", merge_output_format="mp4",
        outtmpl=os.path.join(config.VIDEO_DIR, "%(id)s.%(ext)s"), ffmpeg_location=FFMPEG)
    with yt_dlp.YoutubeDL(opts) as y:
        try:
            y.process_ie_result(info, download=True)
        except Exception as e:
            youtube.raise_if_blocked(e)
            raise
    p = video_path(vid)
    if not p:
        raise RuntimeError("download produced no file")
    return p


def _probe(path):
    return subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr


def duration_of(path):
    for line in _probe(path).splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return None


def has_audio(path):
    """True if the file carries a sound track (videos downloaded by older versions are picture-only)."""
    return any("Audio:" in line for line in _probe(path).splitlines())


def sample_times(start, end, dur, n=None):
    """Centres of equal slices of [start, end], clipped to the video. n defaults to ~1 frame per 5 s (4..12)."""
    if dur:
        end = min(end, dur - 0.5)
    if end <= start:
        return [start] if not dur or start < dur else []
    if n is None:
        n = max(MIN_FRAMES, min(MAX_FRAMES, math.ceil((end - start) / SECONDS_PER_FRAME)))
    step = (end - start) / n
    return [round(start + step * (i + 0.5), 1) for i in range(n)]


def _grab(path, t, raw):
    name = f"{int(round(t * 10)):06d}.jpg"  # named by time (deciseconds), so a file can never be mixed up with another moment
    out = os.path.join(raw, name)
    if not os.path.exists(out):
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", path,
                        "-frames:v", "1", "-q:v", "4", "-y", out], check=False)
    return name if os.path.exists(out) else None


def _font(size):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _sheets(vid, title, rows, raw, tile, prefix, max_h=2600):
    """rows: [(label, [(t, file|None), ...])]. Writes as many sheet images as needed; returns their names."""
    f_lab, f_ts, f_title = _font(15), _font(12), _font(18)
    tw, th = TILE[tile]
    W = max(20 + COLS * (tw + 6), 980)

    def row_h(frames):
        return 40 + max(1, math.ceil(len(frames) / COLS)) * (th + 6) + 10

    pages, cur, h = [], [], 44
    for r in rows:
        if cur and h + row_h(r[1]) > max_h:
            pages.append(cur); cur, h = [], 44
        cur.append(r); h += row_h(r[1])
    if cur:
        pages.append(cur)
    names = []
    for n, page in enumerate(pages, 1):
        img = Image.new("RGB", (W, 44 + sum(row_h(r[1]) for r in page) + 10), "white")
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"{vid}  {title}" + (f"  page {n}/{len(pages)}" if len(pages) > 1 else ""), fill="black", font=f_title)
        y = 44
        for label, frames in page:
            d.text((10, y), "\n".join(textwrap.wrap(label, 118)[:2]), fill=(17, 24, 39), font=f_lab)
            y += 40
            for i, (t, name) in enumerate(frames):
                x, yy = 10 + (i % COLS) * (tw + 6), y + (i // COLS) * (th + 6)
                if name:
                    img.paste(ImageOps.pad(Image.open(os.path.join(raw, name)).convert("RGB"), (tw, th), color="black"), (x, yy))
                else:
                    d.rectangle([x, yy, x + tw, yy + th], fill=(229, 231, 235))
                d.rectangle([x, yy + th - 18, x + 46, yy + th], fill=(0, 0, 0))
                d.text((x + 4, yy + th - 16), fmt(t), fill="white", font=f_ts)
            y += max(1, math.ceil(len(frames) / COLS)) * (th + 6) + 10
        name = f"{prefix}_{n}.jpg"
        img.save(os.path.join(frame_dir(vid), name), quality=85)
        names.append(name)
    return names


def extract(vid, refresh=False):
    """Cut frames for the overview and every subtask. Returns info.json content.
    Reuses existing frames (unless refresh) and an existing video file; downloads only if neither is on disk."""
    if not refresh and info(vid):
        return info(vid)
    with _lock:
        if not refresh and info(vid):  # another worker finished it while we waited
            return info(vid)
        rec = config.load_record(vid)
        path = download(vid)
        dur = duration_of(path)
        fd = frame_dir(vid)
        if os.path.isdir(fd):
            shutil.rmtree(fd)  # older sampling scheme or refresh: start clean so no stale frame is reused
        raw = os.path.join(fd, "raw")
        os.makedirs(raw)
        overview = [[t, _grab(path, t, raw)] for t in sample_times(0, dur, dur, OVERVIEW_FRAMES)]
        first = next((n for _, n in overview if n), None)
        tile = "wide"
        if first:
            w, h = Image.open(os.path.join(raw, first)).size
            tile = "tall" if h > w else "wide"
        subs, rows = {}, []
        for ti, t in enumerate(rec.get("tasks") or []):
            for si, s in enumerate(t.get("subtasks") or []):
                key = f"{ti}.{si}"
                if s.get("start") is None or s.get("end") is None:
                    subs[key] = []
                    rows.append((f"T{ti + 1}.{si + 1} [no timestamp] {s.get('text')}", []))
                    continue
                subs[key] = [[x, _grab(path, x, raw)] for x in sample_times(s["start"], s["end"], dur)]
                past = " [PAST VIDEO END]" if dur and s["start"] >= dur else ""
                rows.append((f"T{ti + 1}.{si + 1} [{fmt(s['start'])}-{fmt(s['end'])}]{past} {s.get('text')}", subs[key]))
        ov_rows = [(f"Whole video {fmt(overview[i][0])}-{fmt(overview[min(i + COLS - 1, len(overview) - 1)][0])}",
                    overview[i:i + COLS]) for i in range(0, len(overview), COLS)]
        sheets = _sheets(vid, f"OVERVIEW (video length {fmt(dur or 0)})", ov_rows, raw, tile, "overview") \
            + _sheets(vid, "TASK FRAMES", rows, raw, tile, "tasks")
        meta = {"version": VERSION, "video_id": vid, "duration": dur, "tile": tile, "overview": overview,
                "subtasks": subs, "sheets": sheets}
        with open(os.path.join(fd, "info.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
        return meta


def _size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs) if os.path.isdir(path) else 0


def delete(vid, keep_frames=False):
    """Delete the downloaded video and audio (and, unless keep_frames, the frames). Never touches the dataset,
    verdicts, transcripts or reviews. Returns bytes freed."""
    freed = 0
    with _lock:
        for p in glob.glob(os.path.join(config.VIDEO_DIR, vid + ".*")) + glob.glob(os.path.join(config.AUDIO_DIR, vid + ".*")):
            freed += _size(p); os.remove(p)
        if not keep_frames and os.path.isdir(frame_dir(vid)):
            freed += _size(frame_dir(vid)); shutil.rmtree(frame_dir(vid))
    return freed


def _files(d, vid="*"):
    return [p for p in glob.glob(os.path.join(d, vid + ".*")) if not p.endswith((".part", ".ytdl"))]


def usage(vid=None):
    if vid:
        return {"video_bytes": sum(_size(p) for p in _files(config.VIDEO_DIR, vid)),
                "audio_bytes": sum(_size(p) for p in _files(config.AUDIO_DIR, vid)),
                "frames_bytes": _size(frame_dir(vid)), "has_frames": bool(info(vid))}
    videos, audio = _files(config.VIDEO_DIR), _files(config.AUDIO_DIR)
    return {"videos": len(videos), "videos_bytes": sum(_size(p) for p in videos),
            "audio_bytes": sum(_size(p) for p in audio),
            "frame_sets": len([d for d in os.listdir(config.FRAME_DIR) if os.path.isdir(os.path.join(config.FRAME_DIR, d))]),
            "frames_bytes": _size(config.FRAME_DIR)}


def downloaded_ids():
    """Videos with a downloaded video or audio file on disk."""
    return sorted({os.path.basename(p).split(".")[0] for p in _files(config.VIDEO_DIR) + _files(config.AUDIO_DIR)})
