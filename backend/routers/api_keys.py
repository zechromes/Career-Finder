"""HTTP routes for provider API keys saved on the Settings page."""

from typing import Literal
from fastapi import APIRouter
from backend.schemas.contracts import ApiKeyInput, ApiKeyStatus

Provider = Literal["openai", "anthropic", "google"]


def build_router(handlers):
    router = APIRouter()

    ###################################
    # - Endpoint: GET /api/settings/keys
    ###################################
    # - Description: Show which providers have a key and where it comes from (settings or .env).
    # - Output: HTTP 200. JSON array of ApiKeyStatus; keys are never returned, only the last 4 chars.
    @router.get("/api/settings/keys", response_model=list[ApiKeyStatus])
    def get_api_keys():
        return handlers.status()

    #############################################
    # - Endpoint: PUT /api/settings/keys/{provider}
    #############################################
    # - Description: Verify the key with the provider, then save it; saved keys override .env.
    # - Output: HTTP 200 with the updated statuses; 422 when the provider rejects the key; 502
    #   when the provider cannot be reached.
    @router.put("/api/settings/keys/{provider}", response_model=list[ApiKeyStatus])
    def save_api_key(provider: Provider, body: ApiKeyInput):
        return handlers.save(provider, body.api_key)

    ################################################
    # - Endpoint: DELETE /api/settings/keys/{provider}
    ################################################
    # - Description: Remove a saved key; the .env value, if any, applies again.
    # - Output: HTTP 200 with the updated statuses.
    @router.delete("/api/settings/keys/{provider}", response_model=list[ApiKeyStatus])
    def remove_api_key(provider: Provider):
        return handlers.remove(provider)

    return router
