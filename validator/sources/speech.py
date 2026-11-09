"""What is SAID in a video, with times. One normalized format for every source:
    [{"id": int|None, "start": float, "end": float, "text": str}, ...]

Sources, best first:
  1. provided  existing Whisper transcripts (TRANSCRIPTS_DIR); subtasks are matched by their segment_ids
  2. whisper   our local speech-to-text of the downloaded audio (non-English audio is translated to English)
  3. youtube   YouTube captions (often rate-limited)
"""
import json, os, threading
import yt_dlp
from .. import config
from . import youtube

_model, _model_lock, _dl_lock = None, threading.Lock(), threading.Lock()


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _norm_whisper(segments):
    return [{"id": s.get("id"), "start": float(s["start"]), "end": float(s["end"]), "text": (s.get("text") or "").strip()}
            for s in segments if s.get("start") is not None]


def cached(vid):
    """(segments, source) from whatever is already available, without downloading or transcribing. (None, None) if none."""
    if config.TRANSCRIPTS_DIR:
        d = _read(os.path.join(config.TRANSCRIPTS_DIR, vid + ".json"))
        if d and d.get("segments"):
            return _norm_whisper(d["segments"]), "provided"
    d = _read(os.path.join(config.WHISPER_DIR, vid + ".json"))
    if d and d.get("segments") is not None:
        return _norm_whisper(d["segments"]), d.get("source", "whisper")
    yt = youtube.get_transcript(vid, fetch=False)
    if yt:
        return [{"id": None, "start": s[0], "end": s[0] + s[1], "text": s[2]} for s in yt], "youtube"
    return None, None


def audio_path(vid):
    """The sound for Whisper: the downloaded video itself when it has a sound track, else a separate audio file."""
    from . import media
    v = media.video_path(vid)
    if v and media.has_audio(v):
        return v
    return media.finished_file(config.AUDIO_DIR, vid)


def download_audio(vid):
    """Only needed when there is no video-with-sound on disk (validation normally downloads video + sound together)."""
    with _dl_lock:
        p = audio_path(vid)
        if p:
            return p
        from .media import NET_RETRY
        info = youtube.take_fresh_info(vid) or youtube.fetch_info(vid)
        opts = youtube.ydl_options(**NET_RETRY, format="ba[ext=m4a]/ba/b",
                                   outtmpl=os.path.join(config.AUDIO_DIR, "%(id)s.%(ext)s"))
        with yt_dlp.YoutubeDL(opts) as y:
            try:
                y.process_ie_result(info, download=True)
            except Exception as e:
                youtube.raise_if_blocked(e)
                raise
        p = audio_path(vid)
        if not p:
            raise RuntimeError("audio download produced no file")
        return p


def _whisper():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # heavy import, only when transcription is actually needed
        _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", download_root=config.MODEL_DIR)
    return _model


def transcribe(vid):
    """Local speech-to-text of the video's audio. Cached in work/whisper/<id>.json."""
    p = os.path.join(config.WHISPER_DIR, vid + ".json")
    if _read(p):
        return _norm_whisper(_read(p)["segments"])
    audio = download_audio(vid)
    with _model_lock:  # CPU-bound; one at a time
        m = _whisper()
        segs, info = m.transcribe(audio, vad_filter=True)
        segs = list(segs)
        task = "transcribe"
        if info.language != "en" and info.language_probability > 0.6:
            segs, _ = m.transcribe(audio, vad_filter=True, task="translate")  # so the judge can read it
            segs, task = list(segs), "translate"
    out = {"source": f"whisper-{config.WHISPER_MODEL}" + (f" (translated from {info.language})" if task == "translate" else ""),
           "language": info.language,
           "segments": [{"id": i, "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for i, s in enumerate(segs)]}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return _norm_whisper(out["segments"])


def get(vid, run_whisper=False):
    """(segments, source). With run_whisper, transcribes locally when nothing is cached."""
    segs, src = cached(vid)
    if segs is None and run_whisper:
        segs = transcribe(vid)
        src = (_read(os.path.join(config.WHISPER_DIR, vid + ".json")) or {}).get("source", "whisper")
    return segs, src


def window(segs, a, b):
    """Text spoken between a and b seconds."""
    return " ".join(s["text"] for s in segs or [] if s["end"] > a and s["start"] < b).strip()


_STOP = set("""about above after again also and another any are because been before being between both but can could did
does doing down during each from further have having here how into its just more most much must now off once only other
our out over own same should some such than that the their them then there these they this those through too under until
very was were what when where which while who why will with would your you yours show shows showing explain explains
describe describes describing note notes mention mentions highlight highlights observe observes discuss discusses
introduce introduces state states provide provides like using used make makes made take takes""".split())


def _words(text):
    """Content-word stems of a text (first 6 letters, so 'harvester'/'harvesting' match)."""
    import re
    return {w[:6] for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOP}


def locate(segs, text, span=3, min_score=0.5):
    """Where in the video is this task actually said? Returns (start, end, score) of the best-matching stretch of
    `span` consecutive speech segments, or None. Rare words count more than common ones (inverse document frequency
    over this video's own transcript), so 'strawberries' or 'kiwi' place a task, while 'farm' or 'plant' do not."""
    import math
    want = _words(text)
    if not segs or len(want) < 2:
        return None
    seg_words = [_words(s["text"]) for s in segs]
    n = len(segs)
    idf = {w: math.log((n + 1) / (1 + sum(w in sw for sw in seg_words))) + 1 for w in want}
    total = sum(idf.values())
    best = None
    for i in range(n):
        words = set().union(*seg_words[i:i + span])
        hit = want & words
        if len(hit) < 2:
            continue
        score = sum(idf[w] for w in hit) / total
        if not best or score > best[2]:
            # report only the segments that actually contain the matched words, and never more than 40 s:
            # speech-to-text can make one segment span minutes of near-silence in vlogs
            inner = [j for j in range(i, min(i + span, n)) if seg_words[j] & hit]
            start = segs[inner[0]]["start"]
            best = (start, min(segs[inner[-1]]["end"], start + 40), round(score, 2))
    return best if best and best[2] >= min_score else None


def for_subtask(segs, source, sub):
    """Speech for one subtask: by its segment_ids when the transcript was provided, else by time window."""
    if source == "provided" and sub.get("segment_ids"):
        ids = set(sub["segment_ids"])
        return " ".join(s["text"] for s in segs if s["id"] in ids).strip()
    if sub.get("start") is None or sub.get("end") is None:
        return ""
    return window(segs, sub["start"], sub["end"])
