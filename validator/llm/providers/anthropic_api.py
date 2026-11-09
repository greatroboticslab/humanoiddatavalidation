"""Claude through Anthropic's official Python SDK (Messages API)."""
import base64
import anthropic
from ... import config
from . import NonRetryable

_client = None


def _get_client():
    global _client
    if _client is None:
        base = config.LLM_URL.rstrip("/")
        for suffix in ("/v1/messages", "/v1"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        kwargs = {"api_key": config.LLM_API_KEY}
        if base and base != "https://api.anthropic.com":  # e.g. a company proxy
            kwargs["base_url"] = base
        _client = anthropic.Anthropic(**kwargs)
    return _client


def _image(path):
    with open(path, "rb") as f:
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.standard_b64encode(f.read()).decode("utf-8")}}


def complete(user, system=None, images=(), max_tokens=1500):
    content = [_image(p) for p in images] + [{"type": "text", "text": user}]
    kwargs = dict(
        model=config.LLM_MODEL,
        # Claude Opus 5.5 always thinks and thinking counts toward max_tokens, so short JSON answers still need room
        max_tokens=max(max_tokens, 16000),
        messages=[{"role": "user", "content": content}],
        output_config={"effort": config.LLM_EFFORT},
        # if a safety classifier declines, the API retries on a fallback model inside the same call
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if system:
        kwargs["system"] = system
    try:
        resp = _get_client().beta.messages.create(**kwargs)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError,
            anthropic.BadRequestError) as e:
        raise NonRetryable(f"{type(e).__name__}: {e}") from e
    # RateLimitError / other APIStatusError / APIConnectionError propagate; the SDK has already retried them twice
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model declined (refusal: {getattr(resp.stop_details, 'category', None)})")
    return "".join(b.text for b in resp.content if b.type == "text")
