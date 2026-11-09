"""Deterministic checks on the dataset record. No LLM needed; these are cheap and exact."""
import collections, re
from .. import config


def check(rec, meta):
    flags = []
    tasks = rec.get("tasks") or []
    dur = (meta or {}).get("duration")
    if meta and meta.get("error"):
        flags.append(("video_unavailable", meta["error"][:120]))
    if rec.get("category") in (None, "", "Unknown Category"):
        flags.append(("no_category", "category is Unknown"))
    if meta and meta.get("title") and rec.get("title"):
        a = set(re.findall(r"\w{4,}", meta["title"].lower())); b = set(re.findall(r"\w{4,}", rec["title"].lower()))
        if a and b and not (a & b):
            flags.append(("title_mismatch_lexical", f"YT: {meta['title'][:60]} | dataset: {rec['title'][:60]}"))
    spans = []
    for i, t in enumerate(tasks):
        s, e = t.get("start"), t.get("end")
        if s is None or e is None or e <= s:
            flags.append(("bad_timestamp", f"task {i}: {s}-{e}"))
        else:
            spans.append((s, e, i))
            if dur and e > dur + 2:
                flags.append(("beyond_video_end", f"task {i} ends {e:.0f}s but video is {dur}s"))
        for j, st in enumerate(t.get("subtasks") or []):
            ss, se = st.get("start"), st.get("end")
            if ss is None or se is None or se <= ss:
                flags.append(("bad_timestamp", f"task {i} sub {j}: {ss}-{se}"))
            elif s is not None and e is not None and (ss < s - 0.5 or se > e + 0.5):
                flags.append(("subtask_outside_task", f"task {i} sub {j}"))
    spans.sort()
    for (s1, e1, i1), (s2, e2, i2) in zip(spans, spans[1:]):
        if s2 < e1 - 0.5:
            flags.append(("tasks_overlap", f"task {i1} [{s1:.1f}-{e1:.1f}] and task {i2} [{s2:.1f}-{e2:.1f}]"))
    flags += chapter_alignment(tasks, (meta or {}).get("chapters"))
    texts = [t.get("task", "") for t in tasks] + [s.get("text", "") for t in tasks for s in t.get("subtasks") or []]
    if len(texts) != len({x.strip().lower() for x in texts}):
        flags.append(("duplicate_tasks", ""))
    return flags


def _stems(text):
    return {w[:5] for w in re.findall(r"[a-z]{5,}", text.lower())}


_RARE = None


def _rare_stems():
    """Stems used by <1% of all subtasks in the dataset. Only these are specific enough to tie a subtask
    to a chapter; common words like 'plants', 'water', 'value' recur all over a video."""
    global _RARE
    if _RARE is None:
        df, n = collections.Counter(), 0
        for vid in config.all_ids():
            for t in config.load_record(vid).get("tasks") or []:
                for s in t.get("subtasks") or []:
                    n += 1
                    df.update(_stems(s.get("text") or ""))
        _RARE = {w for w, c in df.items() if c / max(n, 1) < 0.01}
    return _RARE


def chapter_alignment(tasks, chapters, tol=20.0):
    """Creator-made chapters are ground truth for *when* a topic is covered. If a subtask names a chapter's
    topic but its timestamp lies outside that chapter, the extracted timing points at the wrong footage."""
    if not chapters or len(chapters) < 3:
        return []
    rare = _rare_stems()
    chs = [(c["start_time"], c["end_time"], c["title"], _stems(c["title"])) for c in chapters]
    checked, off = 0, []
    for i, t in enumerate(tasks):
        for j, s in enumerate(t.get("subtasks") or []):
            if s.get("start") is None:
                continue
            words = _stems(s.get("text") or "")
            here = [c for c in chs if c[0] - tol <= s["start"] <= c[1] + tol]
            if any(c[3] & words for c in here):
                checked += 1  # names the topic of the chapter it sits in: aligned
                continue
            hits = [c for c in chs if c[3] & words & rare]
            if len(hits) != 1:
                continue  # no specific topical link, or ambiguous
            cs, ce, title, _ = hits[0]
            checked += 1
            off.append(f"task {i} sub {j} at {s['start']:.0f}s but chapter '{title[:30]}' is {cs:.0f}-{ce:.0f}s")
    if checked >= 2 and len(off) / checked >= 0.5:
        return [("chapter_misaligned", f"{len(off)}/{checked} topic-matched subtasks fall outside their chapter; e.g. " + "; ".join(off[:3]))]
    return []
