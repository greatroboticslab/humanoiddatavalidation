"""OpenAI chat-completions format: local servers (vLLM, LM Studio, Ollama) and api.openai.com."""
import base64
import requests
from ... import config
from . import NonRetryable


def _image(path):
    with open(path, "rb") as f:
        return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()}}


def complete(user, system=None, images=(), max_tokens=1500):
    if not config.LLM_URL:
        raise NonRetryable("LLM_URL is not set: add your LLM server's address to .env (see .env.example)")
    content = [{"type": "text", "text": user}] + [_image(p) for p in images] if images else user
    body = {"model": config.LLM_MODEL,
            "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]}
    if config.LLM_PROVIDER == "vllm":
        # deterministic answers, and switch off Qwen's thinking mode (a vLLM chat-template option)
        body.update(temperature=0, max_tokens=max_tokens, chat_template_kwargs={"enable_thinking": False})
    else:
        # api.openai.com: newer models only take max_completion_tokens, and reasoning models reject temperature
        body["max_completion_tokens"] = max(max_tokens, 4000)
    r = requests.post(config.LLM_URL, json=body, headers={"Authorization": "Bearer " + config.LLM_API_KEY}, timeout=300)
    if r.status_code in (400, 401, 403, 404):
        raise NonRetryable(f"HTTP {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""
