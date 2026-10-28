"""HTTP routes for profiles; business logic stays in the injected handlers."""

from fastapi import APIRouter
from backend.schemas.contracts import RunCreated


def build_router(handlers):
    """Bind request adapters without importing the application or its mutable state."""
    router = APIRouter()

    ######################################################
    # - Endpoint: POST /api/profiles/{profile_id}/searches
    ######################################################
    # - Description: Reopen the latest linked workspace, recovering journal history when
    #   available; fresh=true creates a new workspace.
    # - Output: HTTP 201. JSON {id, runId} identifying the existing or new workspace; no job
    #   search starts automatically.
    @router.post(
        "/api/profiles/{profile_id}/searches",
        response_model=RunCreated,
        status_code=201,
        operation_id="create_search_from_profile",
    )
    async def create_search_from_profile(profile_id: str, fresh: bool = False):
        "Resume the latest linked search, or explicitly create a new search."
        return await handlers.create_search_from_profile(
            profile_id=profile_id, fresh=fresh
        )

    return router
