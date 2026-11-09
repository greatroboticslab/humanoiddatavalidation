"""Planted-error test for the SUBTASK check (frames + speech): does the judge really look and listen, or rubber-stamp?

Takes subtasks the judge already said MATCH, and re-asks with one thing swapped (in memory only):
  wrong task     real frames + speech of the window, task from an unrelated video   -> must be NO
  wrong window   real task, frames + speech from an unrelated video's window        -> must be NO
  repeat         the original, asked again                                          -> must stay YES/PARTLY
and checks that every NO comes with a correct_task.
Run after validating a few videos:   venv\\Scripts\\python -m tests.selftest_subtasks --n 20
"""
import argparse, os, random
from concurrent.futures import ThreadPoolExecutor
from validator import config
from validator.checks import subtask_check
from validator.sources import media


def matched_subtasks():
    out = []
    for f in os.listdir(config.RESULTS_DIR):
        r = subtask_check.load(f[:-5])
        if not r:
            continue
        raw = os.path.join(media.frame_dir(r["video_id"]), "raw")
        title = config.load_record(r["video_id"]).get("title")
        for s in r["subtasks"]:
            if s.get("match") == "YES" and s.get("frames"):
                paths = [os.path.join(raw, n) for n in s["frames"]]
                if all(os.path.exists(p) for p in paths):
                    out.append({**s, "vid": r["video_id"], "title": title, "paths": paths, "src": r.get("speech_source")})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    pool = matched_subtasks()
    if len({p["vid"] for p in pool}) < 2:
        raise SystemExit("Need matching subtasks from at least 2 videos: validate more videos first.")
    targets = rng.sample(pool, min(a.n, len(pool)))

    jobs = []
    for p in targets:
        d = rng.choice([q for q in pool if q["vid"] != p["vid"]])
        jobs += [("wrong_task", p, d, dict(text=d["text"], title=p["title"], start=p["start"], end=p["end"], frame_paths=p["paths"],
                                           spoken_text=p.get("speech", ""), speech_source=p["src"])),
                 ("wrong_window", p, d, dict(text=p["text"], title=p["title"], start=p["start"], end=p["end"], frame_paths=d["paths"],
                                             spoken_text=d.get("speech", ""), speech_source=d["src"])),
                 ("repeat", p, None, dict(text=p["text"], title=p["title"], start=p["start"], end=p["end"], frame_paths=p["paths"],
                                          spoken_text=p.get("speech", ""), speech_source=p["src"]))]

    def run(job):
        kind, p, d, kw = job
        try:
            return kind, p, d, subtask_check.ask_subtask(**kw)
        except Exception as e:
            return kind, p, d, {"error": str(e)}
    with ThreadPoolExecutor(config.LLM_WORKERS) as ex:
        res = list(ex.map(run, jobs))

    def rate(kind, ok):
        rs = [r for r in res if r[0] == kind and "error" not in r[3]]
        hit = sum(ok(r[3]) for r in rs)
        return f"{hit}/{len(rs)} ({100 * hit / max(len(rs), 1):.0f}%)"
    nos = [r for r in res if "error" not in r[3] and r[3].get("match") == "NO"]
    llm = config.describe_llm()
    lines = ["# Subtask check: planted-error self-test", "",
             f"{len(targets)} subtasks the judge said MATCH, from {len({p['vid'] for p in targets})} videos. "
             f"Model: {llm['provider']} / {llm['model']}. Errors: {sum('error' in r[3] for r in res)}.", "",
             "| Planted error | Expected | Caught |", "|---|---|---|",
             f"| Task from an unrelated video on real frames + speech | NO | {rate('wrong_task', lambda x: x.get('match') == 'NO')} |",
             f"| Real task on frames + speech from an unrelated video | NO | {rate('wrong_window', lambda x: x.get('match') == 'NO')} |",
             f"| Original asked again | still YES/PARTLY | {rate('repeat', lambda x: x.get('match') in ('YES', 'PARTLY'))} |",
             f"| Every NO comes with a correct task | correct_task given | {sum(bool((x.get('correct_task') or '').strip()) for *_, x in nos)}/{len(nos)} |",
             "", "## Misses", ""]
    for kind, p, d, x in res:
        if "error" in x:
            continue
        miss = (kind in ("wrong_task", "wrong_window") and x.get("match") != "NO") or (kind == "repeat" and x.get("match") == "NO")
        if miss:
            task = d["text"] if kind == "wrong_task" else p["text"]
            lines.append(f"- **{kind}** `{p['vid']}` T{p['task'] + 1}.{p['sub'] + 1}: task \"{task}\" -> {x.get('match')}. "
                         f"Saw: {x.get('what_is_happening')}")
    lines += ["", "## Example corrections (task from an unrelated video)", ""]
    for kind, p, d, x in [r for r in res if r[0] == "wrong_task" and "error" not in r[3]][:6]:
        lines.append(f"- `{p['vid']}` T{p['task'] + 1}.{p['sub'] + 1} (real: \"{p['text']}\"), planted \"{d['text']}\" -> correct: \"{x.get('correct_task')}\"")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_subtasks.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines)); print("->", out)


if __name__ == "__main__":
    main()
