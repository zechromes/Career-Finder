"""Provider API keys saved from the Settings page; saved keys override .env values."""

import json
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from dotenv import load_dotenv
from fastapi import HTTPException
from backend.paths import API_KEYS_FILE

# Provider -> (label, environment variable the SDKs read, key-check request).
PROVIDERS = {
    "openai": (
        "OpenAI GPT",
        "OPENAI_API_KEY",
        lambda key: URLRequest(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        ),
    ),
    "anthropic": (
        "Anthropic Claude",
        "ANTHROPIC_API_KEY",
        lambda key: URLRequest(
            "https://api.anthropic.com/v1/models?limit=1",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        ),
    ),
    "google": (
        "Google Gemini",
        "GOOGLE_API_KEY",
        lambda key: URLRequest(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
            headers={"x-goog-api-key": key},
        ),
    ),
}
_LOCK = threading.Lock()
# Values from .env or the shell, restored when a saved key is removed.
_ENV_FALLBACK = {}


def _read():
    try:
        return json.loads(API_KEYS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _write(saved):
    API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Owner-only: the file holds credentials.
    fd = os.open(API_KEYS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(saved, handle)


def load():
    """Apply saved keys over .env at startup so every SDK client picks them up."""
    load_dotenv()
    with _LOCK:
        for provider, (_, variable, _) in PROVIDERS.items():
            _ENV_FALLBACK[variable] = os.environ.get(variable)
        for provider, key in _read().items():
            if provider in PROVIDERS:
                os.environ[PROVIDERS[provider][1]] = key


def _provider(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown provider.")
    return PROVIDERS[provider]


def _forget_checks():
    from backend.evaluation.providers import forget_availability

    forget_availability(["claude", "gpt", "gemini"])


def validate(provider, key):
    """Ask the provider to list models: free, and fails only on rejected credentials."""
    try:
        with urlopen(_provider(provider)[2](key), timeout=10):
            return
    except HTTPError as exc:
        if exc.code in {400, 401, 403}:
            raise HTTPException(422, "The provider rejected this API key.") from None
        raise HTTPException(
            502, f"Could not verify the key (provider returned {exc.code}). Try again."
        ) from None
    except (URLError, TimeoutError):
        raise HTTPException(502, "Could not reach the provider to verify the key.") from None


def status():
    saved = _read()
    result = []
    for provider, (label, variable, _) in PROVIDERS.items():
        key = saved.get(provider) or _ENV_FALLBACK.get(variable) or ""
        result.append(
            {
                "provider": provider,
                "label": label,
                "source": "settings" if provider in saved else "env" if key else None,
                # Never return the key itself.
                "hint": f"…{key[-4:]}" if len(key) >= 12 else "",
            }
        )
    return result


def save(provider, key):
    key = key.strip()
    if not key:
        raise HTTPException(422, "Enter an API key.")
    validate(provider, key)
    with _LOCK:
        saved = _read()
        saved[provider] = key
        _write(saved)
        os.environ[PROVIDERS[provider][1]] = key
    _forget_checks()
    return status()


def remove(provider):
    variable = _provider(provider)[1]
    with _LOCK:
        saved = _read()
        saved.pop(provider, None)
        _write(saved)
        if _ENV_FALLBACK.get(variable):
            os.environ[variable] = _ENV_FALLBACK[variable]
        else:
            os.environ.pop(variable, None)
    _forget_checks()
    return status()
