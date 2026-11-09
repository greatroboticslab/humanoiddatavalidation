"""Command line. Run from the project folder (in Docker: docker compose exec dashboard python -m validator ...):

  venv\\Scripts\\python -m validator validate --sample 20 --seed 42    full validation of a random sample
  venv\\Scripts\\python -m validator validate --ids zW3TPU56sw0 --delete-video
  venv\\Scripts\\python -m validator validate --all                   every video (resumable; slow: downloads each one)
  venv\\Scripts\\python -m validator precheck --all                   quick YouTube-info-only pass, to choose what to validate
  venv\\Scripts\\python -m validator report                           rebuild output/: corrected tasks + validation.csv/.html
  venv\\Scripts\\python -m validator rescore                          re-apply rules + verdict logic, no LLM calls
  venv\\Scripts\\python -m validator storage [--delete-all [--keep-frames]]
  venv\\Scripts\\python -m validator agreement                        your dashboard reviews vs the validator
"""
import argparse, json, random, time
from concurrent.futures import ThreadPoolExecutor
from . import config, output, pipeline, report
from .sources import media


def _ids(a):
    if a.ids:
        return a.ids
    ids = config.all_ids()
    return ids if a.all else random.Random(a.seed).sample(ids, min(a.sample, len(ids)))


def _run(ids, fn, workers):
    t0 = time.time()

    def one(v):
        try:
            print(f"{v:>13} {fn(v)}", flush=True)
        except Exception as e:  # one bad video must not stop the run; it is retried next time
            print(f"{v:>13} ERROR {type(e).__name__}: {e}", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, ids))
    print(f"{len(ids)} videos in {time.time() - t0:.0f}s")


def agreement():
    try:
        with open(config.REVIEWS, encoding="utf-8") as f:
            reviews = json.load(f)
    except FileNotFoundError:
        print("No reviews yet: review videos in the dashboard first."); return
    from .checks.verdict import for_video
    rows = [(v, r) for v, r in reviews.items() if r.get("agree")]
    if not rows:
        print("No 'agree with the validator' answers yet."); return
    by = {}
    for v, r in rows:
        by.setdefault(for_video(v).get("verdict") or "not validated", []).append(r["agree"] == "yes")
    ok = sum(sum(x) for x in by.values())
    print(f"you agreed with the validator on {ok}/{len(rows)} videos ({100 * ok / len(rows):.0f}%)")
    for k, x in sorted(by.items()):
        print(f"  {k:16} {sum(x)}/{len(x)}")
    sense = [r.get("makes_sense") for r in reviews.values() if r.get("makes_sense")]
    if sense:
        print("your 'tasks make sense?' answers:", {k: sense.count(k) for k in ("yes", "partly", "no")})


def main():
    ap = argparse.ArgumentParser(prog="python -m validator", description="Validate extracted tasks against their videos.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "precheck"):
        p = sub.add_parser(name)
        g = p.add_mutually_exclusive_group()
        g.add_argument("--ids", nargs="+"); g.add_argument("--all", action="store_true")
        p.add_argument("--sample", type=int, default=20); p.add_argument("--seed", type=int, default=42)
        p.add_argument("--force", action="store_true", help="redo stages that already have a result")
        if name == "validate":
            p.add_argument("--delete-video", action="store_true", help="delete each video/audio file afterwards (frames kept)")
            p.add_argument("--youtube-captions", action="store_true", help="also try YouTube captions (often rate-limited)")
    sub.add_parser("rescore"); sub.add_parser("report"); sub.add_parser("agreement")
    s = sub.add_parser("storage")
    s.add_argument("--delete", nargs="+", metavar="ID"); s.add_argument("--delete-all", action="store_true")
    s.add_argument("--keep-frames", action="store_true")
    a = ap.parse_args()
    if a.cmd in ("validate", "precheck", "rescore", "report") and config.data_problem():
        raise SystemExit(config.data_problem())

    if a.cmd == "validate":
        # downloads and Whisper are serialized inside the package; each video's LLM calls run in parallel
        _run(_ids(a), lambda v: (lambda r: f"{str(r.get('verdict')):15} " + "; ".join(r.get("reasons", []))[:150])(
            pipeline.validate(v, a.force, a.delete_video, a.youtube_captions)), 2)
        print("report:", report.write())
    elif a.cmd == "precheck":
        _run(_ids(a), lambda v: (lambda r: f"{r['llm'].get('verdict'):16} {str(r['llm'].get('summary'))[:80]}")(
            pipeline.text(v, a.force)), config.LLM_WORKERS)
        print("report:", report.write())
    elif a.cmd == "rescore":
        print("rescored", pipeline.rescore(), "pre-check results; corrected task files:", output.write_all(),
              "; report:", report.write())
    elif a.cmd == "report":
        print("corrected task files:", output.write_all(), "in", config.OUTPUT_TASKS_DIR)
        print("report:", report.write())
    elif a.cmd == "agreement":
        agreement()
    elif a.cmd == "storage":
        ids = media.downloaded_ids() if a.delete_all else (a.delete or [])
        if ids:
            freed = sum(media.delete(v, keep_frames=a.keep_frames) for v in ids)
            print(f"deleted {len(ids)} video(s), freed {freed / 1048576:.1f} MB")
        print(media.usage())


if __name__ == "__main__":
    main()
