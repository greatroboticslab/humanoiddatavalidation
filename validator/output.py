"""The output folder, next to data/: one corrected task file per validated video, in the same format as data/.

output/tasks/<video_id>.json is the input record with the corrections applied:
  - a subtask said at another time in the video keeps its text and gets the correct start/end
  - otherwise a subtask judged PARTLY or NO gets the validator's correct task as its text
  - your review wins: a subtask you marked OK stays as it was; your own correction replaces the text
  - a changed subtask keeps the original under "original" and says who changed it in "corrected_by"
  - every checked subtask has a "validation" block, and the record one with the verdict and reasons
It is rebuilt after every validation and every review change."""
import copy, json, os, time
from . import config
from .checks import subtask_check, verdict


def _reviews():
    try:
        with open(config.REVIEWS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _subtask(sub, r, mark, rewrite):
    """The corrected subtask and who corrected it (None if unchanged)."""
    new, by = dict(sub), None
    if rewrite:
        new["text"], by = rewrite, "review"
    elif r and mark != "ok":
        if r.get("correct_time"):
            new["start"], new["end"] = r["correct_time"][:2]
            by = "validator"
        elif r.get("match") != "YES" and (r.get("correct_task") or "").strip():
            new["text"], by = r["correct_task"].strip(), "validator"
    if by:
        new["corrected_by"] = by
        new["original"] = {k: sub.get(k) for k in ("text", "start", "end")}
    if r:
        new["validation"] = {k: r[k] for k in ("match", "issue", "correct_task", "correct_time") if r.get(k)}
        if mark:
            new["validation"]["your_mark"] = mark
    return new, by


def build(vid):
    """The corrected record for one video, or None if it has not been validated yet."""
    fin = verdict.for_video(vid)
    if not fin.get("verdict"):
        return None
    review = _reviews().get(vid) or {}
    marks, rewrites = review.get("tasks") or {}, review.get("rewrites") or {}
    results = subtask_check.load(vid) if fin.get("stage") == "full" else None
    by_pos = {(s["task"], s["sub"]): s for s in (results or {}).get("subtasks", [])}
    rec = copy.deepcopy(config.load_record(vid))
    changed = 0
    for ti, task in enumerate(rec.get("tasks") or []):
        own = (rewrites.get(f"t{ti}") or "").strip()
        if own:
            task["original_task"], task["task"] = task.get("task"), own
            changed += 1
        subs = []
        for si, sub in enumerate(task.get("subtasks") or []):
            key = f"t{ti}.s{si}"
            new, by = _subtask(sub, by_pos.get((ti, si)), marks.get(key), (rewrites.get(key) or "").strip())
            subs.append(new)
            changed += bool(by)
        task["subtasks"] = subs
    rec["validation"] = {"verdict": fin["verdict"], "reasons": fin.get("reasons", []), "corrections": changed,
                         "reviewed": bool(review), "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    return rec


def write(vid):
    """Write (or remove, if not validated) output/tasks/<vid>.json. Returns the path or None."""
    path = os.path.join(config.OUTPUT_TASKS_DIR, vid + ".json")
    rec = build(vid)
    if rec is None:
        if os.path.exists(path):
            os.remove(path)
        return None
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def write_all():
    """Rebuild the output for every video. Returns how many corrected files exist."""
    return sum(write(vid) is not None for vid in config.all_ids())
