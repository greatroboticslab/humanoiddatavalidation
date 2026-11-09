"""Validation dashboard: browse the dataset, run the checks on selected videos, review results, manage downloaded
files. Reads the task files in data/ read-only; writes only under work/.

Start it with run_windows.bat (Windows) or `docker compose up -d` (Linux), or directly:
  python dashboard/app.py [--open]      then open http://127.0.0.1:8765
"""
import csv, io, json, os, random, sys, threading, time
from flask import Flask, Response, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from validator import config, output, pipeline  # noqa: E402
from validator.checks import subtask_check, verdict  # noqa: E402
from validator.sources import media, speech, youtube  # noqa: E402
from jobqueue import JobQueue  # noqa: E402

app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="")
_review_lock = threading.Lock()
_ids_cache = (0, set())


def ids():
    """All video ids, refreshed at most every 30 s."""
    global _ids_cache
    if time.time() - _ids_cache[0] > 30:
        _ids_cache = (time.time(), set(config.all_ids()))
    return _ids_cache[1]


def valid(vid):
    return vid in ids()


def reviews():
    try:
        with open(config.REVIEWS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_summary_cache = {}


def summary(vid):
    p = os.path.join(config.DATA_DIR, vid + ".json")
    mt = os.path.getmtime(p)
    c = _summary_cache.get(vid)
    if not c or c[0] != mt:
        rec = config.load_record(vid)
        tasks = rec.get("tasks") or []
        c = (mt, {"video_id": vid, "title": rec.get("title") or vid,
                  "task_count": len(tasks), "subtask_count": sum(len(t.get("subtasks") or []) for t in tasks)})
        _summary_cache[vid] = c
    return dict(c[1])


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/settings")
def settings():
    return jsonify({"llm": config.describe_llm(), "whisper_model": config.WHISPER_MODEL,
                    "provided_transcripts": bool(config.TRANSCRIPTS_DIR)})


@app.get("/api/videos")
def videos():
    rv, on_disk, queued = reviews(), set(media.downloaded_ids()), QUEUE.active_by_video()
    out = []
    for vid in sorted(ids()):
        s = summary(vid)
        fin = verdict.for_video(vid)
        r = rv.get(vid) or {}
        s.update(verdict=fin["verdict"], precheck=fin.get("precheck"), queue=queued.get(vid),
                 downloaded=vid in on_disk, reviewed=bool(r.get("makes_sense") or r.get("agree")))
        out.append(s)
    return jsonify(out)


@app.get("/api/videos/<vid>")
def video(vid):
    if not valid(vid):
        return jsonify({"error": "not found"}), 404
    return jsonify({"video_id": vid, "record": config.load_record(vid), "meta": youtube.cached_meta(vid),
                    "final": verdict.for_video(vid), "verdicts": verdict.VERDICTS,
                    "validation": pipeline.load_text(vid), "results": subtask_check.load(vid),
                    "media": media.usage(vid), "transcript_source": speech.cached(vid)[1],
                    "queue": QUEUE.active_by_video().get(vid), "review": reviews().get(vid)})


@app.post("/api/videos/<vid>/review")
def save_review(vid):
    if not valid(vid):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True) or {}
    entry = {k: body.get(k) for k in ("makes_sense", "agree", "correct_verdict", "notes", "tasks", "rewrites")}
    entry["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _review_lock:
        rv = reviews()
        rv[vid] = entry
        tmp = config.REVIEWS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rv, f, indent=1)
        os.replace(tmp, config.REVIEWS)
        try:
            output.write(vid)  # your corrections go into output/tasks/<vid>.json
        except Exception as e:  # the review itself is saved either way
            print(f"{vid}: output not updated ({type(e).__name__}: {e})")
    return jsonify(entry)


@app.get("/media/<vid>/<path:name>")
def media_file(vid, name):
    if not valid(vid):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(media.frame_dir(vid), name)  # safe_join blocks ../ escapes


@app.get("/api/storage")
def storage():
    return jsonify({**media.usage(), "downloaded_ids": media.downloaded_ids()})


@app.post("/api/storage/delete")
def storage_delete():
    """Delete downloaded files. Body: {"ids": [...]} or {"all": true}; "keep_frames": true keeps the frames.
    Verdicts, transcripts, visual results and reviews are never deleted."""
    body = request.get_json(force=True) or {}
    targets = media.downloaded_ids() if body.get("all") else [v for v in body.get("ids") or [] if valid(v)]
    if body.get("all") and not body.get("keep_frames"):
        # "everything" also clears frame sets of videos whose download is already gone
        targets = sorted(set(targets) | {d for d in os.listdir(config.FRAME_DIR) if valid(d)})
    freed = sum(media.delete(v, keep_frames=bool(body.get("keep_frames"))) for v in targets)
    return jsonify({"deleted": len(targets), "freed_bytes": freed, **media.usage()})


def _validate(vid, force, delete_after):
    """One queue job: the full validation of one video (YouTube info + frames + speech -> one verdict)."""
    r = pipeline.validate(vid, force, delete_after)
    return {"verdict": r.get("verdict") or "ERROR", "summary": "; ".join(r.get("reasons", []))}


# two videos at a time: downloads and Whisper are serialized inside the package, each video's LLM calls run in parallel
QUEUE = JobQueue(os.path.join(config.WORK, "queue.json"), _validate, workers=2)


@app.post("/api/queue")
def queue_add():
    body = request.get_json(force=True) or {}
    vids = [v for v in body.get("ids") or [] if valid(v)]
    if not vids:
        return jsonify({"error": "no valid video ids"}), 400
    added, skipped = QUEUE.add(vids, bool(body.get("force")), bool(body.get("delete_after")))
    return jsonify({"added": added, "already_queued": skipped})


@app.get("/api/queue")
def queue_list():
    items = QUEUE.list()
    titles = {it["video_id"]: summary(it["video_id"])["title"] for it in items if valid(it["video_id"])}
    for it in items:
        it["title"] = titles.get(it["video_id"], it["video_id"])
    counts = {s: sum(1 for it in items if it["status"] == s) for s in ("queued", "running", "done", "error")}
    return jsonify({"items": items, "counts": counts})


@app.delete("/api/queue/<item_id>")
def queue_remove(item_id):
    r = QUEUE.remove(item_id)
    return (jsonify({"result": r}), 200) if r == "removed" else (jsonify({"error": r}), 409 if r == "running" else 404)


@app.post("/api/queue/<item_id>/retry")
def queue_retry(item_id):
    return jsonify({"ok": QUEUE.retry(item_id)})


@app.post("/api/queue/clear")
def queue_clear():
    return jsonify({"removed": QUEUE.clear_finished()})


@app.get("/api/sample")
def sample():
    n, seed = int(request.args.get("n", 20)), request.args.get("seed")
    rng = random.Random(int(seed)) if seed not in (None, "") else random.Random()
    return jsonify(rng.sample(sorted(ids()), min(n, len(ids()))))


def _task_label(key):
    """Review keys are 0-based ('t3', 't0.s1'); show them as on screen ('T4', 'T1.2')."""
    t, _, s = key.partition(".s")
    return f"T{int(t[1:]) + 1}" + (f".{int(s) + 1}" if s else "")


def _problem(p):
    i = p.get("task_index")
    fix = f" -> correct: {p['correct_task']}" if p.get("correct_task") else ""
    return f"[{f'T{i + 1}' if isinstance(i, int) else 'general'}] {p.get('type')}: {p.get('issue')}{fix}"


@app.get("/api/export.csv")
def export():
    """One row per checked or reviewed video."""
    rv = reviews()
    want = request.args.get("ids")
    vids = [v for v in want.split(",") if valid(v)] if want else sorted(ids())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["video_id", "url", "dataset_title", "youtube_title", "verdict", "reasons", "youtube_info_problems",
                "speech_source", "subtasks_matching", "subtasks_partly", "subtasks_not_matching",
                "validator_corrections", "correct_times", "human_tasks_make_sense", "human_agrees_with_validator",
                "human_verdict", "tasks_marked_wrong", "tasks_marked_ok", "human_corrections", "human_notes"])
    for vid in vids:
        fin, r = verdict.for_video(vid), rv.get(vid) or {}
        if not fin["verdict"] and not r:
            continue  # only validated or reviewed videos
        t, vis = pipeline.load_text(vid), subtask_check.load(vid) or {}
        rec = config.load_record(vid)
        llm = (t or {}).get("llm", {})
        subs = (vis.get("subtasks") or []) if fin["stage"] == "full" else []  # ignore results from the old frames-only version
        tag = lambda s: f"T{s['task'] + 1}.{s['sub'] + 1}"
        pick = lambda f: ", ".join(tag(s) for s in subs if f(s))
        marks = r.get("tasks") or {}
        w.writerow([vid, rec.get("url"), rec.get("title"), (t or {}).get("yt_title"), fin["verdict"] or "not validated",
                    "; ".join(fin.get("reasons", [])), " | ".join(_problem(p) for p in llm.get("problems", [])),
                    vis.get("speech_source") or "",
                    pick(lambda s: s.get("match") == "YES"), pick(lambda s: s.get("match") == "PARTLY"),
                    pick(lambda s: s.get("match") == "NO"),
                    " | ".join(f"{tag(s)}: {s['correct_task']}" for s in subs if (s.get("correct_task") or "").strip()),
                    " | ".join(f"{tag(s)}: {media.fmt(s['correct_time'][0])}-{media.fmt(s['correct_time'][1])}"
                               for s in subs if s.get("correct_time")),
                    r.get("makes_sense") or "", r.get("agree") or "", r.get("correct_verdict") or "",
                    ", ".join(_task_label(k) for k, m in sorted(marks.items()) if m == "wrong"),
                    ", ".join(_task_label(k) for k, m in sorted(marks.items()) if m == "ok"),
                    " | ".join(f"{_task_label(k)}: {v}" for k, v in sorted((r.get("rewrites") or {}).items()) if v),
                    r.get("notes") or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=task_validation.csv"})


def _port_owner(port):
    """None if the port is free, "dashboard" if this dashboard already answers there, else "other"."""
    import socket, urllib.request
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
    except OSError:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings", timeout=3) as r:
            return "dashboard" if "llm" in json.load(r) else "other"
    except Exception:
        return "other"


if __name__ == "__main__":
    import webbrowser
    port = int(os.environ.get("DASHBOARD_PORT", 8765))
    # 127.0.0.1 = reachable from this PC only (the app triggers LLM calls, downloads and deletions).
    # docker-compose.yml sets 0.0.0.0 so the container's port can be published.
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    url = f"http://127.0.0.1:{port}"
    if config.data_problem():
        sys.exit(config.data_problem())
    owner = _port_owner(port)
    if owner == "dashboard":
        print(f"The dashboard is already running: {url}")
        if "--open" in sys.argv:
            webbrowser.open(url)
        sys.exit(0)
    if owner == "other":
        sys.exit(f"Port {port} is used by another program. Set DASHBOARD_PORT in .env to a free port.")
    print(f"Dashboard: {url}  (LLM: {config.describe_llm()['provider']} / {config.LLM_MODEL or 'no model set'})")
    # Our own process id, so tools can stop exactly this server: other "python app.py" processes look identical.
    with open(os.path.join(config.WORK, "dashboard.pid"), "w") as f:
        f.write(str(os.getpid()))
    if "--open" in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    app.run(host=host, port=port, debug=False, threaded=True)
