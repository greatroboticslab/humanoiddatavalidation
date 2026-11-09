"""Exact rules against known cases (no LLM, no network). Run: venv\\Scripts\\python -m tests.test_rules"""
from validator import config
from validator.checks import rules
from validator.sources import youtube

CHAPTER_CASES = {
    "icA_N1AXyr4": True,   # Moringa chapter at 2:46, subtask says 0:21; tasks end at 3:07 of a 13:51 video
    "VA6wnnZcsig": False,  # mulch at 1:47 is inside 'Mulching' 1:08-2:40; pollinate at 9:00 inside 8:32-10:59
    "upgyxjq3TCY": False,  # subtasks sit in their 'Raw material quality' / 'Safety principles' chapters
}


def main():
    failed = 0
    # real videos: needs their cached YouTube info in work/youtube_info (skipped if missing)
    for vid, want in CHAPTER_CASES.items():
        chapters = (youtube.cached_meta(vid) or {}).get("chapters")
        if not chapters:
            print("skip", "chapter_alignment", vid, "(no cached YouTube info)")
            continue
        got = rules.chapter_alignment(config.load_record(vid)["tasks"], chapters)
        ok = bool(got) == want
        failed += not ok
        print("OK  " if ok else "FAIL", "chapter_alignment", vid, got[0][1][:110] if got else "-")

    # synthetic chapters (always run): two subtasks naming a rare topic, inside or outside that topic's chapter
    a, b = sorted(w for w in rules._rare_stems() if w != "intro")[:2]
    chapters = [{"title": "Intro", "start_time": 0, "end_time": 100}, {"title": f"{a} tips", "start_time": 100, "end_time": 200},
                {"title": f"{b} tips", "start_time": 200, "end_time": 300}, {"title": "End", "start_time": 300, "end_time": 400}]
    for name, (sa, sb), want in (("swapped", (250, 120), True), ("in place", (150, 250), False)):
        tasks = [{"subtasks": [{"text": f"Use {a} now", "start": sa}, {"text": f"Use {b} now", "start": sb}]}]
        ok = bool(rules.chapter_alignment(tasks, chapters)) == want
        failed += not ok
        print("OK  " if ok else "FAIL", "chapter_alignment synthetic", name)

    # synthetic record: every exact timestamp rule must fire on its own planted error
    rec = {"category": "Unknown Category", "title": "x", "tasks": [
        {"task": "a", "start": 10, "end": 5, "subtasks": [{"text": "s", "start": 1, "end": 2}]},          # reversed task
        {"task": "b", "start": 20, "end": 60, "subtasks": [{"text": "t", "start": 15, "end": 30}]},       # sub outside
        {"task": "c", "start": 50, "end": 70, "subtasks": [{"text": "u", "start": 50, "end": 70}]},       # overlaps b
        {"task": "d", "start": 200, "end": 260, "subtasks": [{"text": "v", "start": 200, "end": 260}]},   # past end
    ]}
    flags = {k for k, _ in rules.check(rec, {"duration": 120, "title": "x"})}
    for k in ("bad_timestamp", "subtask_outside_task", "tasks_overlap", "beyond_video_end", "no_category"):
        ok = k in flags
        failed += not ok
        print("OK  " if ok else "FAIL", "planted", k)
    # speech.locate: where a mistimed task is really said.
    # needs the cached Whisper transcripts in work/whisper (skipped if missing).
    from validator.sources import speech
    LOCATE_CASES = [  # (video, words of the task, expected window in seconds)
        ("W5A6cwxYMSM", "Notice the robot picking only ripe strawberries with precision.", (130, 180)),
        ("W5A6cwxYMSM", "Look at the harvester picking and transporting Kiwi fruits.", (175, 215)),
        ("W5A6cwxYMSM", "Notice the UAVs being used for precise pesticide spraying.", (540, 580)),
        ("8NS1330coc4", "Prepare a bed for growing onions, beans, and other vegetables.", (1700, 1790)),
        ("ZR0PUHxyz0c", "Watch the engine and wet clutch assembly in action for extra cutting power.", (25, 70)),
    ]
    for vid, text, (lo, hi) in LOCATE_CASES:
        segs, _ = speech.cached(vid)
        if not segs:
            print("skip", "locate", vid, "(no cached transcript)")
            continue
        loc = speech.locate(segs, text)
        ok = bool(loc) and lo <= loc[0] <= hi
        failed += not ok
        print("OK  " if ok else "FAIL", "locate", vid, f"{text[:40]}… -> {loc}")
    print("\nall passed" if not failed else f"\n{failed} FAILED")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
