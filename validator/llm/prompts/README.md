# Prompts

Every instruction the validator sends to the LLM lives in this folder, so it can be read and changed without
touching code. `${name}` placeholders are filled in by `llm.prompt()`.

| File | Used by | Sent with |
|---|---|---|
| `precheck_system.txt` | `checks/precheck.py` | System message for the pre-check |
| `precheck_answer_format.txt` | `checks/precheck.py` | Appended after the evidence (YouTube info + dataset tasks + rule flags) |
| `subtask_check.txt` | `checks/subtask_check.py` | One call per subtask, with the frames from that subtask's time range. `${n} ${start} ${end} ${title} ${text}` |
| `subtask_fix.txt` | `checks/subtask_check.py` | Only when a subtask was criticized but no correction came back: asks for just the corrected subtask. |
| `video_overview.txt` | `checks/subtask_check.py` | One call per video, with 8 frames spread across the whole video. `${n} ${title} ${length}` |

`subtask_check.txt` gets the frames AND the speech of the subtask's own time range and answers YES / PARTLY / NO:
lenient about wording (a task that says "observe X" matches if X is said; extra content in the window does not
count against it) and strict about facts (a different crop, tool, number, name or step makes it PARTLY).
Whenever a subtask is not YES it must give a `correct_task`; `precheck_answer_format.txt` likewise requires a
`correct_task` for every problem.

After changing a prompt, re-run the self-tests (`tests/`) to check the validator still catches planted errors.
The final verdicts are computed in code from the model's answers (`precheck.verdict`, `verdict.combine`),
not chosen by the model.
