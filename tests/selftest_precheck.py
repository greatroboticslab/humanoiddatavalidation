"""Planted-error test for the TEXT check: does it catch errors we know are there?

Corrupts in-memory copies of real records (the task files are never touched) and checks each corruption
is detected. Uses cached YouTube metadata only.   Run: venv\\Scripts\\python -m tests.selftest_precheck --n 20
"""
import argparse, copy, os, random, re
from concurrent.futures import ThreadPoolExecutor
from validator import config, pipeline
from validator.checks import precheck, rules
from validator.sources import youtube


def words(t):
    return set(re.findall(r"[a-z]{4,}", (t or "").lower()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    pool = [v for v in config.all_ids() if pipeline.load_text(v) and (youtube.cached_meta(v) or {}).get("duration")]
    targets = rng.sample(pool, min(a.n, len(pool)))
    titles = {v: words(youtube.cached_meta(v).get("title")) for v in pool}

    jobs = []
    for v in targets:
        rec, meta = config.load_record(v), youtube.cached_meta(v)
        d = rng.choice([x for x in pool if x != v and not (titles[x] & titles[v])])  # unrelated donor video
        drec = config.load_record(d)
        swap = copy.deepcopy(rec); swap.update(tasks=drec["tasks"], title=drec["title"], reason=drec["reason"])
        tswap = copy.deepcopy(rec); tswap["title"] = drec["title"]
        jobs += [("swap_tasks", v, d, swap, meta), ("swap_title", v, d, tswap, meta)]

    def work(job):
        kind, v, d, rec, meta = job
        return kind, v, d, precheck.judge(rec, meta, None, rules.check(rec, meta))
    with ThreadPoolExecutor(config.LLM_WORKERS) as ex:
        results = list(ex.map(work, jobs))

    shift_hit = 0
    for v in targets:
        rec, meta = copy.deepcopy(config.load_record(v)), youtube.cached_meta(v)
        for t in rec["tasks"]:
            for o in [t] + (t.get("subtasks") or []):
                for k in ("start", "end"):
                    if o.get(k) is not None:
                        o[k] += meta["duration"] + 60
        shift_hit += any(k == "beyond_video_end" for k, _ in rules.check(rec, meta))

    base = [pipeline.load_text(v)["llm"] for v in targets]
    swap = [r for r in results if r[0] == "swap_tasks"]
    tsw = [r for r in results if r[0] == "swap_title"]
    pct = lambda x, n: f"{x}/{n} ({100 * x / max(n, 1):.0f}%)"
    lines = ["# Text check: planted-error self-test", "", f"{len(targets)} real videos, seed {a.seed}, metadata-only evidence.", "",
             "| Planted error | Expected | Result |", "|---|---|---|",
             f"| none (original records) | not called MISMATCH | false MISMATCH: {pct(sum(b.get('verdict') == 'MISMATCH' for b in base), len(base))} |",
             f"| tasks swapped in from an unrelated video | MISMATCH | caught: {pct(sum(r[3].get('verdict') == 'MISMATCH' for r in swap), len(swap))} |",
             f"| only the title swapped | title flagged, not MISMATCH | title caught: {pct(sum(r[3].get('dataset_title_matches_video') is False for r in tsw), len(tsw))}; "
             f"wrongly MISMATCH: {pct(sum(r[3].get('verdict') == 'MISMATCH' for r in tsw), len(tsw))} |",
             f"| all timestamps moved past the video end | beyond_video_end | caught: {pct(shift_hit, len(targets))} |", ""]
    lines += ["## Missed swaps", ""] + [f"- `{v}` given tasks of `{d}` -> {r.get('verdict')}: {r.get('summary')}"
                                        for _, v, d, r in swap if r.get("verdict") != "MISMATCH"]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_precheck.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[:11])); print("->", out)


if __name__ == "__main__":
    main()
