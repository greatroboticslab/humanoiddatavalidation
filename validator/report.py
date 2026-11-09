"""Batch reports: output/validation.csv (for Excel) and output/validation.html (readable, worst first)."""
import csv, html, os
from . import config, pipeline
from .checks import subtask_check, verdict
from .sources import youtube


def _tlabel(p):
    i = p.get("task_index")
    return f"T{i + 1}" if isinstance(i, int) else "general"


def rows():
    out = []
    for vid in config.all_ids():
        t, vis, meta = pipeline.load_text(vid), subtask_check.load(vid), youtube.cached_meta(vid)
        if not t and not vis:
            continue
        rec = config.load_record(vid)
        out.append({"id": vid, "url": rec.get("url"), "dataset_title": rec.get("title"), "yt_title": (meta or {}).get("title"),
                    "final": verdict.combine(t, vis, meta), "text": (t or {}).get("llm", {}), "flags": (t or {}).get("flags", []),
                    "results": vis or {}})
    order = {k: i for i, k in enumerate(verdict.ORDER)}
    out.sort(key=lambda r: (order.get(r["final"]["verdict"], 99), r["id"]))
    return out


def write():
    rs = rows()
    with open(os.path.join(config.OUTPUT_DIR, "validation.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "url", "verdict", "reasons", "precheck_verdict", "content_match", "about_farming", "title_ok",
                    "subtasks_not_matching", "corrected_subtasks", "youtube_info_problems", "flags", "dataset_title", "yt_title"])
        for r in rs:
            fin, t, subs = r["final"], r["text"], r["results"].get("subtasks", [])
            tag = lambda s: f"T{s['task'] + 1}.{s['sub'] + 1}"
            w.writerow([r["id"], r["url"], fin["verdict"] or "not validated", "; ".join(fin.get("reasons", [])),
                        t.get("verdict"), t.get("content_match"), t.get("about_farming"), t.get("dataset_title_matches_video"),
                        ", ".join(tag(s) for s in subs if s.get("match") == "NO"),
                        " | ".join(f"{tag(s)}: {s['correct_task']}" for s in subs if (s.get("correct_task") or "").strip()),
                        " | ".join(f"[{_tlabel(p)}] {p.get('type')}: {p.get('issue')}"
                                   + (f" -> correct: {p['correct_task']}" if p.get("correct_task") else "") for p in t.get("problems", [])),
                        "; ".join(k for k, _ in r["flags"]), r["dataset_title"], r["yt_title"]])
    counts = {}
    for r in rs:
        k = r["final"]["verdict"] or "not validated"
        counts[k] = counts.get(k, 0) + 1
    esc = html.escape
    cards = []
    for r in rs:
        fin = r["final"]
        v = fin["verdict"] or "NOTVALIDATED"
        reasons = "".join(f"<li>{esc(x)}</li>" for x in fin.get("reasons", []))
        sugg = "".join(f"<li>T{s['task'] + 1}.{s['sub'] + 1}: <s>{esc(s['text'])}</s> → {esc(s['correct_task'])}</li>"
                       for s in r["results"].get("subtasks", []) if (s.get("correct_task") or "").strip())
        pre = "" if fin["verdict"] else f" (pre-check: {esc(str(fin.get('precheck')))})"
        cards.append(f"<div class='c {v}'><b>{esc(fin['verdict'] or 'not validated')}</b>{pre} "
                     f"<a href='{esc(r['url'] or '')}'>{esc(r['id'])}</a>"
                     f"<div>dataset: {esc(str(r['dataset_title']))}<br>youtube: {esc(str(r['yt_title']))}</div>"
                     f"<ul>{reasons}</ul>{f'<p><b>Suggested corrections</b></p><ul>{sugg}</ul>' if sugg else ''}</div>")
    with open(os.path.join(config.OUTPUT_DIR, "validation.html"), "w", encoding="utf-8") as f:
        f.write("<meta charset=utf-8><title>Validation report</title><style>body{font:14px system-ui;max-width:900px;margin:2em auto;padding:0 1em}"
                ".c{border-left:5px solid #999;padding:.5em 1em;margin:.7em 0;background:#f6f6f6}.DOES_NOT_MATCH{border-color:#c00}"
                ".UNAVAILABLE{border-color:#555}.PARTLY_MATCHES{border-color:#e90}.MATCHES{border-color:#090}</style>"
                f"<h1>Validation report</h1><p>{len(rs)} videos: {counts}</p>" + "".join(cards))
    return len(rs), counts
