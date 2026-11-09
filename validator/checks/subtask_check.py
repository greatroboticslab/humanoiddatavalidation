"""Subtask check: for each subtask, shows the model the frames AND the speech from that subtask's own time range and
asks one question: does what is going on here match the task as written? If not, it must give the corrected task."""
import json, os, time
from concurrent.futures import ThreadPoolExecutor
from .. import config, llm
from ..sources import media, speech

SCHEMA = 3  # bump when the result format changes; older results are treated as "not validated"
#           (correct_time / correct_time_score are optional additions, so results without them stay valid)
MATCH = ("YES", "PARTLY", "NO")
# Speech text sent per subtask. ~15 chars per second of talking, so this covers a ~10-minute window: every word spoken
# in the subtask's range reaches the model. Longer windows are cut, and the result says so (speech_truncated).
MAX_SPEECH_CHARS = 9000


def ask_subtask(text, title, start, end, frame_paths, spoken_text="", speech_source=None):
    """One judgment: the task + its frames + its speech. Used by judge() and by the planted-error self-test."""
    speech_txt = (spoken_text or "")[:MAX_SPEECH_CHARS]
    a = llm.ask_json(llm.prompt("subtask_check.txt", n=len(frame_paths), start=media.fmt(start), end=media.fmt(end),
                                title=title, text=text, speech=speech_txt or "(no speech text for this range)",
                                speech_source=f"speech-to-text, source: {speech_source}" if speech_source and speech_txt else "no transcript available"),
                     images=frame_paths, max_tokens=400)
    if a.get("match") not in MATCH:
        a["match"] = "NO"
    if len(spoken_text or "") > MAX_SPEECH_CHARS:
        a["speech_truncated"] = True
    if a["match"] == "YES":
        a["correct_task"] = ""  # nothing to correct
    elif not (a.get("correct_task") or "").strip():
        # a criticized task must always come with its correction: ask once more, for just that
        try:
            a["correct_task"] = llm.ask_json(llm.prompt(
                "subtask_fix.txt", n=len(frame_paths), start=media.fmt(start), end=media.fmt(end), title=title, text=text,
                speech=speech_txt or "(none)", issue=a.get("issue") or "it does not match this time range"),
                images=frame_paths, max_tokens=200).get("correct_task", "")
        except llm.LLMError:
            pass
    return a


def _place(r, segs):
    """A subtask that does not match its own window may simply be at the wrong time: find where its words are said
    in the transcript. If that is elsewhere, record it as the correct time (and, when the dataset gave no usable
    timestamp at all, keep the task text as the correction, since only its time is wrong)."""
    loc = speech.locate(segs, r.get("text"))
    if not loc:
        return
    start, end = r.get("start"), r.get("end")
    no_time = start is None or end is None or end <= start
    if not no_time and loc[0] < end + 5 and loc[1] > start - 5:
        return  # best match is (around) its own window: not a timing problem
    r["correct_time"] = [round(loc[0], 1), round(loc[1], 1)]
    r["correct_time_score"] = loc[2]
    if no_time and not (r.get("correct_task") or "").strip():
        r["correct_task"] = r.get("text")
        r["issue"] = f"no usable timestamp in the dataset; the task is said at {media.fmt(loc[0])}-{media.fmt(loc[1])}"


def counts(subs):
    return {k: sum(1 for s in subs if s.get("match") == k) for k in MATCH}


def judge(vid):
    rec = config.load_record(vid)
    inf = media.info(vid)
    if not inf:
        raise RuntimeError("no frames: run media.extract first")
    raw = os.path.join(media.frame_dir(vid), "raw")
    title = rec.get("title")
    segs, src = speech.cached(vid)

    def one(item):
        (ti, si), s = item
        pairs = [(t, n) for t, n in inf["subtasks"].get(f"{ti}.{si}", []) if n]
        said = speech.for_subtask(segs, src, s) if segs else ""
        base = {"task": ti, "sub": si, "start": s.get("start"), "end": s.get("end"), "text": s.get("text"),
                "frames": [n for _, n in pairs], "times": [t for t, _ in pairs], "speech": said}
        if not pairs:
            r = {**base, "match": "NO", "what_is_happening": "",
                 "issue": "no frames: the timestamp is missing or past the end of the video", "correct_task": ""}
        else:
            try:
                r = {**base, **ask_subtask(s.get("text"), title, s["start"], s["end"],
                                           [os.path.join(raw, n) for _, n in pairs], said, src)}
            except llm.LLMError as e:
                return {**base, "error": str(e)}
        if r["match"] != "YES":
            _place(r, segs)
        return r

    items = [((ti, si), s) for ti, t in enumerate(rec.get("tasks") or []) for si, s in enumerate(t.get("subtasks") or [])]
    ov = [os.path.join(raw, n) for _, n in inf["overview"][::2] if n]
    with ThreadPoolExecutor(config.LLM_WORKERS) as ex:
        ov_future = ex.submit(llm.ask_json, llm.prompt("video_overview.txt", n=len(ov), title=title,
                                                       length=media.fmt(inf["duration"] or 0)), None, ov, 300)
        subs = list(ex.map(one, items))
        try:
            overview = ov_future.result()
        except llm.LLMError as e:
            overview = {"error": str(e)}
    ok = [s for s in subs if "error" not in s]
    out = {"video_id": vid, "schema": SCHEMA, "frames_version": inf["version"], "match_counts": counts(ok),
           "speech_source": src, "overview": overview, "subtasks": subs, "errors": len(subs) - len(ok),
           "llm": {k: v for k, v in config.describe_llm().items() if k != "key_set"},
           "judged": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(config.RESULTS_DIR, vid + ".json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return out


def load(vid):
    """The current result for a video, or None (also None for results made by older versions of this check)."""
    try:
        with open(os.path.join(config.RESULTS_DIR, vid + ".json"), encoding="utf-8") as f:
            r = json.load(f)
        return r if r.get("schema") == SCHEMA else None
    except Exception:
        return None
