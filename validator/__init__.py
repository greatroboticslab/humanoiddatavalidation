"""Validates the tasks extracted from YouTube farming videos against the videos themselves.

  config.py       paths and settings (read from the project's .env)
  pipeline.py     validate(): runs one video through every step below, with caching
  output.py       output/tasks/<video_id>.json: the corrected task file (same format as data/)
  report.py       output/validation.csv + .html
  cli.py          command line (python -m validator ...)

  sources/        collecting the evidence
    youtube.py      YouTube title, description, chapters and captions
    media.py        video download (once), frames per subtask, disk usage, delete
    speech.py       what is said, with times: provided transcript > local Whisper > YouTube captions

  checks/         judging the tasks
    rules.py        exact checks on the task record (timestamps, overlaps, chapters); no AI
    precheck.py     the tasks vs the YouTube title, description and chapters
    subtask_check.py  each subtask vs the frames + speech of its own time range: yes/partly/no + correct task
    verdict.py      one verdict per video, computed in code

  llm/            talking to the LLM
    client.py       the one entry point for LLM calls: fills prompts, parses JSON
    providers/      one module per API: openai_compatible, anthropic_api
    prompts/        every instruction sent to the LLM, as plain text files
"""
