"""Thin wrapper around the OpenAI SDK (GPT-6 Luna).

Secrets used (in .streamlit/secrets.toml):
    OPENAI_API_KEY   required
    LLM_MODEL        default "gpt-6-luna"
    OPENAI_BASE_URL  optional, only if the professor's key goes through a proxy
"""
import json
from functools import lru_cache

from openai import OpenAI

from BackEnd.config import get_secret

DEFAULT_MODEL = "gpt-6-luna"


class LLMError(RuntimeError):
    """Raised when the model can't be reached or returns unusable output."""


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise LLMError("OPENAI_API_KEY is missing from .streamlit/secrets.toml")
    return OpenAI(api_key=key, base_url=get_secret("OPENAI_BASE_URL") or None, timeout=60)


def model_name() -> str:
    return get_secret("LLM_MODEL", DEFAULT_MODEL)


def parse_json(text: str) -> dict:
    """Parse a JSON object, tolerating a model that wraps it in prose or ``` fences."""
    text = (text or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"Model did not return JSON: {text[:120]!r}")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned broken JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("Model returned JSON, but not an object")
    return data


def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """One chat call whose answer must be a JSON object."""
    try:
        resp = _client().chat.completions.create(
            model=model_name(),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_completion_tokens=max_tokens,
        )
    except LLMError:
        raise
    except Exception as e:  # network, auth, quota, unknown model …
        raise LLMError(f"LLM call failed: {e}") from e
    return parse_json(resp.choices[0].message.content)


def ping() -> dict:
    """Smoke test: python -c "from BackEnd.llm import ping; print(ping())" """
    return complete_json("Reply only with JSON.", 'Return exactly {"ok": true}.', max_tokens=50)