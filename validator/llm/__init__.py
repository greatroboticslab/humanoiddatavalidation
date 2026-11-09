"""LLM access: client.py sends requests, providers/ holds one module per API, prompts/ holds every instruction."""
from .client import LLMError, ask_json, parse_json, prompt  # noqa: F401
