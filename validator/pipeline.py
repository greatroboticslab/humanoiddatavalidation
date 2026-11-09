"""Runs one video through validation, with caching. Used by the CLI and the dashboard.
validate() is the one entry point; text() is its YouTube-info stage, also usable alone as a quick pre-check."""
import json, os
from . import config, output
from .checks import precheck, rules, subtask_check, verdict
from .sources import media, speech, youtube


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_text(vid):
    return _read(os.path.join(config.PRECHECK_DIR, vid + ".json"))


def text(vid, force=False):
    """YouTube-info stage (title, description, chapters + any transcript already available). Cached unless force."""
    p = os.path.join(config.PRECHECK_DIR, vid + ".json")
    if not force and os.path.exists(p):
        return _read(p)
    rec = config.load_record(vid)
    meta = youtube.get_meta(vid)
    segs, src = (None, None) if meta.get("error") else speech.cached(vid)  # provided > our Whisper > YouTube
    flags = rules.check(rec, meta)
    if meta.get("error"):
        v = {"verdict": precheck.verdict({}, flags, unavailable=True), "evidence": "none", "content_match": "UNVERIFIABLE",
             "summary": "Source video is unavailable on YouTube (" + meta["error"][:80] + "), so tasks cannot be verified."}
    else:
        v = precheck.judge(rec, meta, segs, flags)
        if segs:
            v["evidence"] = f"transcript ({src})+metadata"
    out = {"id": vid, "url": rec.get("url"), "dataset_title": rec.get("title"), "yt_title": meta.get("title"),
           "channel": meta.get("channel"), "duration": meta.get("duration"), "flags": flags, "llm": v}
    if v.get("verdict") != "ERROR":  # errors are not cached, so the next run retries them
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    return out


def validate(vid, force=False, delete_video_after=False, use_youtube_captions=False):
    """THE validation: every source of evidence for one video, then one verdict.
      1. YouTube info (title, description, chapters); stops here if the video is gone
      2. video frames for every subtask's time range
      3. what is said in those windows (provided transcript > local Whisper > YouTube captions)
      4. text judgment: tasks vs YouTube info + transcript; exact timestamp rules
      5. per-subtask judgment: frames + speech, with suggested replacements
      6. one verdict (verdict.combine)
    Nothing is downloaded twice: the video, its frames and its transcript are reused whenever they exist.
    force (Re-validate) only redoes the judging: the LLM checks and the verdict."""
    meta = youtube.get_meta(vid)
    if meta.get("error"):
        text(vid, force=force)  # records UNAVAILABLE
        output.write(vid)
        return verdict.combine(load_text(vid), None, meta)
    media.extract(vid)  # no-op when the frames exist; downloads only when neither frames nor video are on disk
    if use_youtube_captions:
        youtube.get_transcript(vid, fetch=True)
    try:
        speech.get(vid, run_whisper=True)
    except ImportError as e:  # the speech-to-text tool itself is missing: fail loudly rather than judge without speech
        raise RuntimeError("speech-to-text is not installed (run run_windows.bat again, or "
                           "pip install -r requirements.txt); retry this job once it is") from e
    except youtube.YouTubeBlocked:  # YouTube refused for now: the job waits and retries, never judged without speech
        raise
    except Exception as e:  # no audio track, download refused...: judged from frames alone, and the verdict says so
        print(f"{vid}: no transcript ({type(e).__name__}: {e})")
    segs, src = speech.cached(vid)
    t = load_text(vid)
    text(vid, force=force or not t or bool(segs and "transcript" not in str(t["llm"].get("evidence"))))
    v = subtask_check.load(vid)
    if force or not v or v.get("frames_version") != media.VERSION or (segs and v.get("speech_source") != src):
        subtask_check.judge(vid)
    if delete_video_after:
        media.delete(vid, keep_frames=True)  # frames are the evidence shown in the dashboard; the files are not needed
    output.write(vid)  # output/tasks/<vid>.json: the corrected task file
    return verdict.for_video(vid)


def rescore():
    """Re-apply rules and the pre-check verdict logic to cached results. No YouTube or LLM calls.
    (The final verdict is always computed fresh by verdict.combine, so it needs no rescoring.)"""
    n = 0
    for f in os.listdir(config.PRECHECK_DIR):
        p = os.path.join(config.PRECHECK_DIR, f)
        r = _read(p)
        if not r:
            continue
        meta = youtube.cached_meta(r["id"]) or {}
        r["flags"] = rules.check(config.load_record(r["id"]), meta)
        r["llm"]["verdict"] = precheck.verdict(r["llm"], r["flags"], unavailable=bool(meta.get("error")))
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1)
        n += 1
    return n
