# validator: the validation engine

Checks whether the tasks extracted from each YouTube video match what is going on in that video. It only **reads** the
task files in `data/`; corrected task files and reports go to `output/`, working files to `work/`.

## Layout

```
validator/
  config.py            paths and settings, read from the project's .env
  pipeline.py          validate(): runs one video through every step, with caching
  output.py            output/tasks/<video_id>.json: the corrected task file (same format as data/)
  report.py            output/validation.csv + .html
  cli.py               command line (python -m validator ...)
  sources/             collecting the evidence
    youtube.py           YouTube title, description, chapters and captions
    media.py             video download (once), frames per subtask, disk usage, delete
    speech.py            what is said, with times: provided transcript > local Whisper > YouTube captions;
                         also finds where in the transcript a subtask is actually said
  checks/              judging the tasks
    rules.py             exact checks on the task record (timestamps, overlaps, chapters, duplicates); no AI
    precheck.py          the tasks vs the YouTube title, description and chapters
    subtask_check.py     each subtask: its frames + speech vs the subtask -> YES / PARTLY / NO + correct task / time
    verdict.py           the one verdict per video, computed in code
  llm/                 talking to the LLM
    client.py            the one entry point for LLM calls: fills prompts, parses JSON
    providers/           one module per API: openai_compatible (local servers / OpenAI), anthropic_api (Claude)
    prompts/             every instruction sent to the LLM, as plain text files (see prompts/README.md)
```

What it writes, one file or folder per video:

```
work/
  youtube_info/        title, description, chapters        videos/     downloaded videos (deletable)
  youtube_captions/    YouTube captions                    audio/      audio tracks (deletable)
  whisper/             our speech-to-text                  frames/     frames per subtask (deletable)
  precheck/            pre-check results                   models/     the Whisper model
  results/             per-subtask results                 reviews.json  your reviews from the dashboard
```

## How a video is checked

1. **YouTube info:** the title, description and creator chapters are fetched, and the exact rules run (timestamps
   inside the video, subtasks inside their task, overlaps, chapter alignment). A quick pre-check compares the tasks
   with this information.
2. **Video and speech:** the video (360p, with audio) is downloaded once. Speech comes from the transcripts in
   `TRANSCRIPTS_DIR` if set, otherwise from a local Whisper run (non-English audio is translated).
3. **Each subtask:** frames are cut inside its own time range (one about every 5 s, 4–12 per subtask). The LLM gets
   them together with the speech of the same window. It answers whether what is shown and said there matches the
   subtask: **YES / PARTLY / NO**, what is happening instead, and the **correct task** whenever it is not YES. If the
   subtask is said elsewhere in the video, `speech.locate` gives the **correct time**.
4. **Verdict:** `verdict.combine` turns the answers into one label per video: MATCHES / PARTLY_MATCHES /
   DOES_NOT_MATCH / UNAVAILABLE, with reasons. The model never picks the label.
5. **Your review** in the dashboard is the ground truth.

## Run (from the project folder)

On Windows use `venv\Scripts\python`. With Docker use `docker compose exec dashboard python`.

```bash
python -m validator validate --sample 20 --seed 42      # full validation of a random sample
python -m validator validate --ids zW3TPU56sw0 --delete-video
python -m validator validate --all                      # every video (resumable; slow: downloads each one)
python -m validator precheck --all                      # quick YouTube-info-only pass
python -m validator report                              # rebuild output/: corrected task files + validation.csv/.html
python -m validator rescore                             # re-apply rules + verdict logic, no LLM calls
python -m validator storage [--delete-all [--keep-frames]]
python -m validator agreement                           # your dashboard reviews vs the validator
```

## Tests

```bash
python -m tests.test_rules            # exact rules and transcript search, no network
python -m tests.test_jobqueue         # the dashboard's background job queue
python -m tests.test_no_redownload    # a video already on disk is never downloaded again
python -m tests.selftest_precheck     # planted errors, pre-check      -> tests/selftest_precheck.md
python -m tests.selftest_subtasks     # planted errors, per subtask    -> tests/selftest_subtasks.md
```

Re-run the self-tests after changing a prompt or switching the LLM provider/model.

## Switching LLM

Edit `.env` (see `.env.example`): `LLM_PROVIDER` = `vllm` | `openai` | `anthropic`, plus `LLM_URL`, `LLM_API_KEY`,
`LLM_MODEL`. The model must accept images.
