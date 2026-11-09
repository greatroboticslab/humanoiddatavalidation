# MTSU Task Validation

Checks whether the tasks extracted from YouTube farming videos **match what is going on in each video** at their
timestamps. For every subtask it looks at frames from that subtask's time range and reads what is said there, asks an
LLM whether they match, and suggests the correct task (and the correct time) when they don't. A web dashboard runs
the validations and lets you review the results while watching the videos.

The task files are in `data/`, one `<video_id>.json` per video.

## Quick start

### Windows

**Option 1: one click.** Double-click **`run_windows.bat`**.

- **First run:** it finds Python 3.10–3.14 (or installs Python 3.12 with winget), creates `venv\`, installs
  `requirements.txt`, and creates `.env` from `.env.example`. Notepad opens: fill in the `LLM_*` settings, save, close.
- **Later runs:** it starts straight away and opens http://127.0.0.1:8765.
- **Stop:** close the window.

**Option 2: by hand.** Needs Python 3.10–3.14. In a terminal (Command Prompt or PowerShell) in the project folder:

```bat
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Fill in the `LLM_*` settings in `.env`, then start the dashboard:

```bat
venv\Scripts\python dashboard\app.py --open
```

`--open` opens http://127.0.0.1:8765 in the browser. Later runs need only this last command. Stop: Ctrl+C.

### Linux (Docker)

```bash
cp .env.example .env        # fill in the LLM_* settings
docker compose up -d        # the first start builds the image
```

Open http://localhost:8765. Logs: `docker compose logs -f`. Stop: `docker compose down`. After updating the code:
`docker compose up -d --build`.

## Settings (`.env`)

| Setting | What it is |
|---|---|
| `LLM_PROVIDER`, `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL` | The LLM: a local OpenAI-compatible server (vLLM, LM Studio, Ollama), OpenAI, or Anthropic (Claude). The model must accept images |
| `DASHBOARD_PORT` | Dashboard port, default 8765 |
| `WHISPER_MODEL` | Local speech-to-text model: `tiny` / `base` / `small` / `medium` |
| `TRANSCRIPTS_DIR` | Optional: existing Whisper transcripts |
| `YT_COOKIES_FROM_BROWSER`, `YT_COOKIES` | Optional: sign in to YouTube (browser login or a cookies.txt) if it blocks downloads with "confirm you're not a bot" |

## Validating

1. On the **Dataset** tab, select videos (tick cards, **20-video sample** or **Random 20**) and click **Validate**.
   Jobs run in the background on the **Jobs** tab. For each video it:
   - reads the YouTube title, description and chapters;
   - downloads the video (360p, with sound) once;
   - for every subtask, takes a frame about every 5 s inside its time range (4–12 frames) and the words said in that
     same window (local Whisper speech-to-text);
   - asks the LLM whether what is shown and said there **matches the subtask** (yes / partly / no), with **the correct
     subtask** and, if it is said at another time, **the correct time**;
   - gives the video one verdict: **Matches · Partly matches · Does not match · Unavailable**.
2. Open a video to review it: each subtask shows its frames, what was said, the result and the correction. Mark
   subtasks ✓/✗ and accept or edit corrections. Everything saves automatically.
3. **Output:** every validated video gets a corrected task file, `output/tasks/<video_id>.json`, in the same format
   as `data/`: wrong subtasks get the correct text or time (your corrections win), with the original kept next to
   it. **Export CSV** gives one row per video with the verdict, reasons, corrections and your answers.

If YouTube asks this computer to slow down ("confirm you're not a bot"), the jobs wait and retry by themselves
(after 15, 30, then 60 minutes); signing in to YouTube (`YT_COOKIES_FROM_BROWSER` or `YT_COOKIES`) avoids it.

Command line: `python -m validator validate --sample 20` (see `validator/README.md`).

## Project layout

```
run_windows.bat        start on Windows
docker-compose.yml     start on Linux / Docker
requirements.txt       Python packages
.env.example           settings template (copy to .env)

data/                  input: the task files that are validated, one <video_id>.json per video
output/                output: corrected task files (output/tasks/) and validation.csv / .html (not in git)
validator/             the validation engine (see validator/README.md)
  sources/               collecting the evidence: YouTube info, video and frames, speech
  checks/                judging: exact rules, pre-check, per-subtask check, verdict
  llm/                   LLM client, one provider per API, and every prompt
dashboard/             web dashboard: Flask app.py + static/ (HTML, CSS, JavaScript)
tests/                 offline tests and planted-error self-tests (with their latest results)
scripts/               stop_dashboard.ps1
work/                  working files: downloads, frames, transcripts, intermediate results, reviews (not in git)
```
