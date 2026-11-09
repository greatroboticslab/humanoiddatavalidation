"""Paths and settings. Values come from the project's .env file; real environment variables take precedence."""
import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PKG_DIR)
PROMPT_DIR = os.path.join(PKG_DIR, "llm", "prompts")


def _load_dotenv(path):
    """Minimal .env reader: KEY=VALUE lines, # comments (also after a value), optional quotes. Existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if v and v[0] in "\"'" and v[0] in v[1:]:
                v = v[1:v.index(v[0], 1)]                 # "quoted value" (may contain #)
            else:
                v = v.split(" #", 1)[0].split("\t#", 1)[0].strip()   # value   # comment
            os.environ.setdefault(k.strip(), v)


_load_dotenv(os.path.join(ROOT, ".env"))

# Task files to validate, one <video_id>.json per video. Only read, never written.
DATA_DIR = os.path.join(ROOT, "data")
# Optional: existing Whisper transcripts, one <video_id>.json with "segments" per video.
TRANSCRIPTS_DIR = os.environ.get("TRANSCRIPTS_DIR") or None

# Output, next to data/: the corrected task files (same format as data/) and the CSV/HTML reports
OUTPUT_DIR = os.path.join(ROOT, "output")
OUTPUT_TASKS_DIR = os.path.join(OUTPUT_DIR, "tasks")

# Working files created at run time (caches and intermediate results, one file or folder per video)
WORK = os.path.join(ROOT, "work")
YOUTUBE_INFO_DIR = os.path.join(WORK, "youtube_info")      # title, description, chapters
CAPTIONS_DIR = os.path.join(WORK, "youtube_captions")      # YouTube captions (when YouTube allows it)
VIDEO_DIR = os.path.join(WORK, "videos")                   # downloaded videos (deletable)
AUDIO_DIR = os.path.join(WORK, "audio")                    # downloaded audio tracks (deletable)
WHISPER_DIR = os.path.join(WORK, "whisper")                # our speech-to-text of the audio
FRAME_DIR = os.path.join(WORK, "frames")                   # frames cut from the videos (deletable)
MODEL_DIR = os.path.join(WORK, "models")                   # the Whisper model, downloaded on first use
PRECHECK_DIR = os.path.join(WORK, "precheck")              # results of the YouTube-info pre-check
RESULTS_DIR = os.path.join(WORK, "results")                # results of the per-subtask check
REVIEWS = os.path.join(WORK, "reviews.json")               # your reviews from the dashboard

# --- LLM ---------------------------------------------------------------------------------------------------------
# LLM_PROVIDER: "vllm" (local OpenAI-compatible server, e.g. Qwen), "openai", or "anthropic".
# If unset it is inferred from LLM_URL, so switching provider is usually just changing the URL, key and model.
# There is no built-in server address: LLM_URL comes from .env (OpenAI and Anthropic have defaults).
_PROVIDER = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
_DEFAULT_URL = {"openai": "https://api.openai.com/v1/chat/completions", "anthropic": "https://api.anthropic.com"}
LLM_URL = os.environ.get("LLM_URL") or _DEFAULT_URL.get(_PROVIDER, "")
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("LLM_KEY", "EMPTY")
LLM_PROVIDER = _PROVIDER or ("anthropic" if "anthropic.com" in LLM_URL else "openai" if "openai.com" in LLM_URL else "vllm")
_DEFAULT_MODEL = {"vllm": "Qwen/Qwen3.8-27B", "anthropic": "claude-opus-5-5", "openai": ""}
LLM_MODEL = os.environ.get("LLM_MODEL") or _DEFAULT_MODEL.get(LLM_PROVIDER, "")
LLM_WORKERS = int(os.environ.get("LLM_WORKERS", "4"))
# Anthropic only: thinking depth (low | medium | high | xhigh | max). Claude Opus 5.5 always thinks.
LLM_EFFORT = os.environ.get("LLM_EFFORT", "medium")

# --- Speech-to-text (used when no transcript is available) --------------------------------------------------------
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")   # tiny | base | small | medium (bigger = slower, better)

# Optional YouTube sign-in, for when YouTube asks this computer to confirm it is not a bot. Off by default.
COOKIES = os.environ.get("YT_COOKIES")                              # a cookies.txt file exported from a browser
COOKIES_FROM_BROWSER = os.environ.get("YT_COOKIES_FROM_BROWSER")    # or read them from a browser: firefox, edge, chrome...

for d in (OUTPUT_TASKS_DIR, YOUTUBE_INFO_DIR, CAPTIONS_DIR, VIDEO_DIR, AUDIO_DIR, WHISPER_DIR, FRAME_DIR, MODEL_DIR,
          PRECHECK_DIR, RESULTS_DIR):
    os.makedirs(d, exist_ok=True)


def describe_llm():
    """Safe summary for logs and the dashboard (never includes the key)."""
    return {"provider": LLM_PROVIDER, "model": LLM_MODEL, "url": LLM_URL, "key_set": LLM_API_KEY not in ("", "EMPTY")}


def data_problem():
    """Why the task files cannot be read (a message for the user), or None when they can."""
    hint = "Put the task files (one <video_id>.json per video) in the data folder."
    if not os.path.isdir(DATA_DIR):
        return f"Task folder not found: {DATA_DIR}\n{hint}"
    if not any(f.endswith(".json") for f in os.listdir(DATA_DIR)):
        return f"No task files (*.json) in {DATA_DIR}\n{hint}"
    return None


def all_ids():
    return sorted(f[:-5] for f in os.listdir(DATA_DIR) if f.endswith(".json"))


def load_record(vid):
    import json
    with open(os.path.join(DATA_DIR, vid + ".json"), encoding="utf-8") as f:
        return json.load(f)
