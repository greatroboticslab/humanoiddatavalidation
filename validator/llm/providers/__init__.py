"""One module per LLM API. Each exposes complete(user, system, images, max_tokens) -> reply text.

  openai_compatible   a local OpenAI-compatible server (vLLM, LM Studio, Ollama) and OpenAI itself
  anthropic_api       Claude, through Anthropic's official SDK

Which one is used is decided by config.LLM_PROVIDER (set in .env, or inferred from LLM_URL).
"""


class NonRetryable(RuntimeError):
    """A request that will fail the same way again (bad key, bad model name, malformed request)."""
