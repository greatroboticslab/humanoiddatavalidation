"""YouTube-info check: compares the extracted tasks with what YouTube says about the video (title, description,
chapters, transcript when available). Part of validation, and usable alone as a quick pre-check.
The LLM fills in fixed fields; verdict() turns them into the pre-check label."""
from .. import llm
from ..sources import speech


def verdict(v, flags, unavailable=False):
    """Pre-check label, computed from the judge's fields (not chosen by the LLM)."""
    if unavailable:
        return "UNAVAILABLE"
    types = {p.get("type") for p in v.get("problems") or []}
    # a content mismatch must cite wrong content (the judge sometimes says MISMATCH over timing or title only)
    if v.get("content_match") == "MISMATCH" and "wrong_content" in types:
        return "DOES_NOT_MATCH"
    if v.get("content_match") == "MATCH" and v.get("dataset_title_matches_video") is not False \
            and not any(k in ("chapter_misaligned", "beyond_video_end", "bad_timestamp") for k, _ in flags):
        return "MATCHES"
    return "PARTLY_MATCHES"


def evidence(rec, meta, segs, flags):
    """The data part of the message: real video on one side, dataset record on the other.
    segs: speech.py segments (or None)."""
    L = ["== REAL VIDEO (from YouTube) =="]
    if meta.get("error"):
        L.append("VIDEO UNAVAILABLE: " + meta["error"][:150])
    else:
        L.append(f"title: {meta.get('title')}\nchannel: {meta.get('channel')}\nduration_s: {meta.get('duration')}\n"
                 f"youtube_category: {meta.get('categories')}\ntags: {meta.get('tags')}")
        L.append("description: " + (meta.get("description") or "")[:700].replace("\n", " "))
        if meta.get("chapters"):
            L.append("chapters: " + "; ".join(f"{c['start_time']:.0f}s {c['title']}" for c in meta["chapters"][:15]))
    L.append(f"transcript available: {'yes' if segs else 'NO (judging from metadata only)'}")
    L.append("\n== DATASET RECORD ==")
    L.append(f"dataset title: {rec.get('title')}\ndataset 'relevant' reason: {rec.get('reason')}")
    for i, t in enumerate(rec.get("tasks") or []):
        L.append(f"TASK {i} [{t.get('start')}-{t.get('end')}s]: {t.get('task')}")
        if segs and t.get("start") is not None and t.get("end") is not None:
            # a sample of what is said per task is enough for this topic-level check; the subtask check gets all of it
            L.append("   spoken in this window (first part): " + speech.window(segs, t["start"], t["end"])[:1500])
        for s in (t.get("subtasks") or [])[:6]:
            L.append(f"   - [{s.get('start')}-{s.get('end')}] {s.get('text')}")
    if flags:
        L.append("\n== AUTOMATIC FLAGS ==\n" + "\n".join(f"{k}: {v}" for k, v in flags[:10]))
    return "\n".join(L)


def judge(rec, meta, segs, flags):
    try:
        v = llm.ask_json(evidence(rec, meta, segs, flags) + "\n\n" + llm.prompt("precheck_answer_format.txt"),
                         system=llm.prompt("precheck_system.txt"))
    except llm.LLMError as e:
        return {"verdict": "ERROR", "summary": "LLM judge failed: " + str(e), "evidence": "n/a"}
    v["evidence"] = "transcript+metadata" if segs else "metadata_only"
    v["verdict"] = verdict(v, flags)
    return v
