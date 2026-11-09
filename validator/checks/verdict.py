"""The single verdict for a video: do its tasks match what is going on in it?
Combined from every source of evidence:
  - each subtask vs the frames + speech of its own time range (subtask_check)
  - the tasks vs the YouTube title, description and chapters (precheck)
  - exact timestamp rules (rules.py)
Pure function of the cached results: changing the thresholds here re-labels every video without new LLM calls."""

VERDICTS = {
    "MATCHES":        "What is going on in the video matches the tasks: most subtasks match their time range.",
    "PARTLY_MATCHES": "Some subtasks match what is going on at their time, others do not. See the corrections.",
    "DOES_NOT_MATCH": "Most subtasks do not match what is going on at their time, or the tasks describe a different video.",
    "UNAVAILABLE":    "The video is private or deleted on YouTube, so the tasks cannot be checked.",
}
ORDER = ["DOES_NOT_MATCH", "PARTLY_MATCHES", "UNAVAILABLE", "MATCHES"]
MATCHES_AT, DOES_NOT_MATCH_BELOW = 0.75, 0.40  # share of subtasks matching (PARTLY counts half)
_TIMING_FLAGS = {"beyond_video_end": "some timestamps are past the end of the video",
                 "bad_timestamp": "some timestamps are missing or reversed",
                 "chapter_misaligned": "subtasks sit outside the YouTube chapter that covers their topic",
                 "tasks_overlap": "tasks overlap in time"}


def combine(text, subtasks_result, meta):
    """text: pipeline.load_text() or None; subtasks_result: subtask_check.load() or None; meta: YouTube metadata.
    Returns {"verdict", "reasons": [...], "stage": "full" | "precheck" | "none"}."""
    if (meta or {}).get("error"):
        return {"verdict": "UNAVAILABLE", "reasons": [VERDICTS["UNAVAILABLE"]], "stage": "full"}
    t = (text or {}).get("llm", {})
    if not subtasks_result:
        # only the quick YouTube-info pass exists: not validated yet
        return {"verdict": None, "precheck": t.get("verdict"), "reasons": [], "stage": "precheck" if text else "none"}

    subs = [s for s in subtasks_result.get("subtasks", []) if "error" not in s]
    n = len(subs)
    c = {k: sum(1 for s in subs if s.get("match") == k) for k in ("YES", "PARTLY", "NO")}
    score = (c["YES"] + 0.5 * c["PARTLY"]) / n if n else 0
    # subtasks whose words are said at another time in the video (subtask_check located them in the transcript)
    elsewhere = sum(1 for s in subs if s.get("correct_time"))
    types = [p.get("type") for p in t.get("problems") or []]
    timing = elsewhere >= max(2, 0.3 * n) or (types.count("wrong_timestamp") >= types.count("wrong_content") > 0)
    # "a different video" only when the content itself is wrong, not when the tasks are this video's at the wrong times
    content_wrong = t.get("content_match") == "MISMATCH" and "wrong_content" in types and not timing

    reasons = [f"{c['YES']} of {n} subtasks match what is going on at their time, {c['PARTLY']} partly, {c['NO']} do not"]
    if elsewhere:
        reasons.append(f"{elsewhere} subtask(s) are said at a different time in the video: their timestamps are wrong "
                       f"(the correct times are shown per subtask)")
    src = subtasks_result.get("speech_source")
    reasons.append(f"judged from the frames and the speech ({src})" if src else "no transcript was available: judged from the frames alone")
    if t:
        topic = ("describe a different video" if content_wrong else "are about this video but placed at the wrong times" if timing
                 else "fit the topic" if t.get("content_match") == "MATCH" else "partly fit the topic")
        reasons.append(f"YouTube title/description: tasks {topic}"
                       + ("" if t.get("dataset_title_matches_video", True) else "; the dataset title does not match the video"))
        if t.get("about_farming") is False:
            reasons.append("note: the video is not about farming")
    for k, _ in (text or {}).get("flags", []):
        if k in _TIMING_FLAGS and _TIMING_FLAGS[k] not in reasons:
            reasons.append(_TIMING_FLAGS[k])

    if content_wrong or score < DOES_NOT_MATCH_BELOW:
        v = "DOES_NOT_MATCH"
    elif score >= MATCHES_AT:
        v = "MATCHES"
    else:
        v = "PARTLY_MATCHES"
    return {"verdict": v, "reasons": reasons, "stage": "full", "match_counts": c, "subtasks": n}


def for_video(vid):
    from .. import pipeline
    from ..sources import youtube
    from . import subtask_check
    return combine(pipeline.load_text(vid), subtask_check.load(vid), youtube.cached_meta(vid))
