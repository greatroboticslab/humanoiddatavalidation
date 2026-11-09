"""The one entry point for LLM calls: picks the provider from config, fills prompt files, returns parsed JSON."""
import json, os, re, time
from string import Template
from .. import config
from .providers import NonRetryable


class LLMError(RuntimeError):
    pass


def _provider():
    if config.LLM_PROVIDER == "anthropic":
        from .providers import anthropic_api as p  # imported lazily: only needed when Claude is configured
    else:
        from .providers import openai_compatible as p
    return p


_prompts = {}


def prompt(name, **fields):
    """Load validator/llm/prompts/<name> and fill its ${placeholders}."""
    if name not in _prompts:
        with open(os.path.join(config.PROMPT_DIR, name), encoding="utf-8") as f:
            _prompts[name] = Template(f.read().strip())
    return _prompts[name].substitute(**fields) if fields else _prompts[name].template


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


def ask_json(user, system=None, images=(), max_tokens=1500, retries=2):
    """Send one message (optionally with images) and return the JSON object in the reply."""
    err = None
    for attempt in range(retries + 1):
        try:
            return parse_json(_provider().complete(user, system=system, images=list(images), max_tokens=max_tokens))
        except NonRetryable as e:
            raise LLMError(str(e)[:300]) from e  # bad key / model / request: retrying won't help
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(2 * (attempt + 1))
    raise LLMError(err)
