"""Validation queue: one persistent list of jobs, worked off in order by background workers.
Survives page changes (it lives in the server) and server restarts (it is saved to work/queue.json)."""
import json, os, threading, time, uuid

STATUSES = ("queued", "running", "done", "error")
MAX_WAITS = 3  # a job whose error says "retry at <time>" (e.g. YouTube asked to slow down) waits at most this often


class JobQueue:
    def __init__(self, path, run, workers=2):
        """run(video_id, force, delete_after) -> {"verdict", "summary"}; called on a worker thread.
        If run raises an error with a retry_at time, the job waits in the queue until then and runs again."""
        self.path, self.run = path, run
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.items = self._load()
        for it in self.items:  # a restart interrupted these: do them again
            if it["status"] == "running":
                it.update(status="queued", started=None, verdict=None, summary="", error="")
        self._save()
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    # --- persistence -------------------------------------------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=1)
        os.replace(tmp, self.path)

    # --- public API (all thread-safe) --------------------------------------------------------------------------
    def add(self, video_ids, force=False, delete_after=False):
        """Queue videos; a video already queued or running is not added twice."""
        with self.lock:
            active = {it["video_id"] for it in self.items if it["status"] in ("queued", "running")}
            new = [{"id": uuid.uuid4().hex[:10], "video_id": v, "force": force, "delete_after": delete_after,
                    "status": "queued", "added": time.time(), "started": None, "finished": None,
                    "verdict": None, "summary": "", "error": "", "not_before": None, "waits": 0, "note": ""} for v in dict.fromkeys(video_ids) if v not in active]
            self.items += new
            self._save()
            self.wake.notify_all()
            return len(new), len(video_ids) - len(new)

    def list(self):
        with self.lock:
            return [dict(it) for it in self.items]

    def active_by_video(self):
        with self.lock:
            return {it["video_id"]: it["status"] for it in self.items if it["status"] in ("queued", "running")}

    def remove(self, item_id):
        """Cancel a queued job or forget a finished one. A running job cannot be stopped mid-way."""
        with self.lock:
            it = next((x for x in self.items if x["id"] == item_id), None)
            if not it:
                return "not found"
            if it["status"] == "running":
                return "running"
            self.items.remove(it)
            self._save()
            return "removed"

    def retry(self, item_id):
        with self.lock:
            it = next((x for x in self.items if x["id"] == item_id), None)
            if not it or it["status"] not in ("error", "done"):
                return False
            if any(x["video_id"] == it["video_id"] and x["status"] in ("queued", "running") for x in self.items):
                return False  # the same video is already queued or validating in another job
            it.update(status="queued", added=time.time(), started=None, finished=None, error="", force=True,
                      verdict=None, summary="", not_before=None, waits=0, note="")  # no old result while it runs again
            self._save()
            self.wake.notify_all()
            return True

    def clear_finished(self):
        with self.lock:
            n = len(self.items)
            self.items = [it for it in self.items if it["status"] in ("queued", "running")]
            self._save()
            return n - len(self.items)

    # --- worker ------------------------------------------------------------------------------------------------
    def _next(self):
        """The first queued job that may run now; jobs waiting for a retry time are skipped until then."""
        with self.lock:
            while True:
                now = time.time()
                it = next((x for x in self.items if x["status"] == "queued" and (x.get("not_before") or 0) <= now), None)
                if it:
                    it.update(status="running", started=now)
                    self._save()
                    return it
                later = [x["not_before"] for x in self.items if x["status"] == "queued" and x.get("not_before")]
                self.wake.wait(timeout=max(1.0, min(later) - now) if later else None)

    def _worker(self):
        while True:
            it = self._next()
            try:
                res = self.run(it["video_id"], it["force"], it["delete_after"])
                upd = dict(status="done", verdict=res.get("verdict"), summary=res.get("summary", ""),
                           not_before=None, note="", finished=time.time())
            except Exception as e:  # one failed video never stops the queue
                retry_at = getattr(e, "retry_at", None)
                if retry_at and it.get("waits", 0) < MAX_WAITS:  # temporary: back in the queue until then
                    upd = dict(status="queued", started=None, not_before=retry_at, waits=it.get("waits", 0) + 1,
                               note=str(e)[:400])
                else:
                    upd = dict(status="error", error=f"{type(e).__name__}: {e}"[:400], not_before=None, note="",
                               finished=time.time())
            with self.lock:
                if it in self.items:  # (it is the same dict object held in self.items)
                    it.update(**upd)
                    self._save()
                    self.wake.notify_all()
