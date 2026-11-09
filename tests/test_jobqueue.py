"""The dashboard's validation queue, with a fake validation step (no LLM, no network).
Run: venv\\Scripts\\python -m tests.test_jobqueue"""
import json, os, sys, tempfile, threading, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard"))
import jobqueue  # noqa: E402
from jobqueue import JobQueue  # noqa: E402


def wait(cond, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.02)
    return False


def main():
    failed = 0

    def check(name, ok):
        nonlocal failed
        failed += not ok
        print("OK  " if ok else "FAIL", name)

    path = os.path.join(tempfile.mkdtemp(), "queue.json")
    gate, slow_gate, ran = threading.Event(), threading.Event(), []
    slow_gate.set()

    class Later(RuntimeError):  # like YouTubeBlocked: "try again at retry_at"
        def __init__(self, retry_at):
            super().__init__("try later")
            self.retry_at = retry_at

    def run(vid, force, delete_after):
        ran.append(vid)
        gate.wait(5)
        if vid == "slow":
            slow_gate.wait(5)
        if vid == "busy" and ran.count("busy") == 1:
            raise Later(time.time() + 0.5)
        if vid == "never":
            raise Later(time.time() + 0.05)
        if vid == "bad":
            raise RuntimeError("download failed")
        return {"verdict": "MATCHES", "summary": f"ok {vid}"}

    q = JobQueue(path, run, workers=2)
    added, skipped = q.add(["a", "b", "c", "a"])
    check("duplicates in one request are added once", (added, skipped) == (3, 1))
    check("two run at a time, in order", wait(lambda: sorted(ran) == ["a", "b"]))
    check("a running job cannot be removed", q.remove(next(i["id"] for i in q.list() if i["video_id"] == "a")) == "running")
    check("an already queued video is not added again", q.add(["c"]) == (0, 1))
    check("a queued job can be cancelled", q.remove(next(i["id"] for i in q.list() if i["video_id"] == "c")) == "removed")
    q.add(["bad"])
    gate.set()
    check("all finish", wait(lambda: all(i["status"] in ("done", "error") for i in q.list())))
    st = {i["video_id"]: i for i in q.list()}
    check("results recorded", st["a"]["status"] == "done" and st["a"]["verdict"] == "MATCHES")
    check("a failure is recorded and does not stop the queue", st["bad"]["status"] == "error" and "download failed" in st["bad"]["error"])
    check("cancelled job never ran", "c" not in ran)
    check("retry re-queues a failed job", q.retry(st["bad"]["id"]) and wait(lambda: ran.count("bad") == 2))
    # a video validating in one job cannot be retried from an older, finished job of the same video
    q.add(["slow"])
    wait(lambda: any(i["video_id"] == "slow" and i["status"] == "done" for i in q.list()))
    old = next(i["id"] for i in q.list() if i["video_id"] == "slow")
    slow_gate.clear()
    q.add(["slow"])
    wait(lambda: ran.count("slow") == 2)
    check("retry refused while the same video is validating", q.retry(old) is False)
    slow_gate.set()
    wait(lambda: all(i["status"] in ("done", "error") for i in q.list()))
    check("retry allowed again once it finished", q.retry(old) and wait(lambda: ran.count("slow") == 3))
    # "try again later" errors: the job waits in the queue (with a note), then runs again by itself
    t0 = time.time()
    q.add(["busy"])
    check("a 'try later' job goes back to the queue with a note",
          wait(lambda: any(i["video_id"] == "busy" and i["status"] == "queued" and i["note"] for i in q.list())))
    check("it runs again by itself once the time comes, and finishes",
          wait(lambda: any(i["video_id"] == "busy" and i["status"] == "done" for i in q.list())) and time.time() - t0 >= 0.5
          and ran.count("busy") == 2)
    q.add(["never"])
    check("it gives up after MAX_WAITS tries and shows the error",
          wait(lambda: any(i["video_id"] == "never" and i["status"] == "error" for i in q.list()))
          and ran.count("never") == 1 + jobqueue.MAX_WAITS)
    check("clear finished keeps nothing finished", wait(lambda: all(i["status"] != "running" for i in q.list())) and q.clear_finished() >= 2)

    # restart: a job that was running when the server stopped is queued again and finishes
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"id": "x1", "video_id": "z", "force": False, "delete_after": False, "status": "running", "added": 0,
                    "started": 1, "finished": None, "verdict": None, "summary": "", "error": ""}], f)
    q2 = JobQueue(path, run, workers=1)
    check("an interrupted job resumes after a restart", wait(lambda: q2.list()[0]["status"] == "done"))
    with open(path, encoding="utf-8") as f:
        check("the queue is saved to disk", json.load(f)[0]["status"] == "done")
    print("\nall passed" if not failed else f"\n{failed} FAILED")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
