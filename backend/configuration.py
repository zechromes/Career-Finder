"""Configuration operations, separate from HTTP route declarations."""

import json
import os
import threading
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen
from backend.profiles.extraction import PROFILE_MODELS, profile_model_id
from backend.evaluation.providers import evaluation_model_options

DEFAULT_EVALUATION_PROVIDER = os.getenv("EVALUATION_PROVIDER", "claude")
if DEFAULT_EVALUATION_PROVIDER not in {"claude", "gemini", "gpt"}:
    DEFAULT_EVALUATION_PROVIDER = "claude"
LOCATION_CACHE = {}
LOCATION_CACHE_LOCK = threading.Lock()


# List the configured evaluation providers for the frontend.
def get_evaluation_models():
    return evaluation_model_options()


# List the supported resume extraction choices.
def get_profile_models():
    names = {
        "openai": "OpenAI GPT",
        "anthropic": "Anthropic Claude",
        "gemini": "Google Gemini",
        "mistral": "Mistral",
    }
    return [
        {
            "value": key,
            "label": f"{names[key]} · {profile_model_id(key)}",
            "model_id": profile_model_id(key),
        }
        for key in PROFILE_MODELS
    ]


# Expose public defaults without returning provider credentials.
def get_config():
    return {
        "evaluation_mode": "all",
        "evaluation_models": evaluation_model_options(),
        "evaluation_provider": DEFAULT_EVALUATION_PROVIDER,
        "max_upload_bytes": 5 * 1024 * 1024,
        "max_pdf_pages": 20,
        "retention_days": 7,
    }


def suggest_locations(q: str = ""):
    """Return worldwide city, region, and country suggestions from Photon."""
    query = q.strip()
    if len(query) < 2:
        return []

    cache_key = query.casefold()
    with LOCATION_CACHE_LOCK:
        if cache_key in LOCATION_CACHE:
            return LOCATION_CACHE[cache_key]

    # Photon is queried server-side so the browser only talks to our API and
    # the provider's response format stays out of the Vue components.
    params = [
        ("q", query),
        ("limit", "8"),
        ("layer", "city"),
        ("layer", "locality"),
        ("layer", "state"),
        ("layer", "country"),
    ]
    request = URLRequest(
        "https://photon.komoot.io/api/?" + urlencode(params),
        headers={"User-Agent": "CareerTracker/1.0 location-search"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # Suggestions are helpful but not required to run a search.
        print(f"Location suggestions unavailable: {exc}")
        return []

    suggestions = []
    seen = set()
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        name = properties.get("name")
        if not name:
            continue
        parts = [name, properties.get("state"), properties.get("country")]
        label = ", ".join(dict.fromkeys(str(part) for part in parts if part))
        if label.casefold() not in seen:
            seen.add(label.casefold())
            suggestions.append({"label": label, "value": label})

    with LOCATION_CACHE_LOCK:
        LOCATION_CACHE[cache_key] = suggestions
    return suggestions
