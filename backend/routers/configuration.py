"""HTTP routes for configuration; business logic stays in the injected handlers."""

from fastapi import APIRouter
from backend.schemas.contracts import ModelOption


def build_router(handlers):
    """Bind request adapters without importing the application or its mutable state."""
    router = APIRouter()

    ########################################
    # - Endpoint: GET /api/evaluation-models
    ########################################
    # - Description: Compatibility alias, hidden from API docs. List configured providers and
    #   model IDs for job-fit evaluation.
    # - Output: HTTP 200. JSON array of ModelOption objects: value, label and model_id.
    @router.get(
        "/api/evaluation-models",
        response_model=list[ModelOption],
        include_in_schema=False,
    )

    ########################################
    # - Endpoint: GET /api/models/evaluation
    ########################################
    # - Description: List configured providers and model IDs for job-fit evaluation.
    # - Output: HTTP 200. JSON array of ModelOption objects: value, label and model_id.
    @router.get(
        "/api/models/evaluation",
        response_model=list[ModelOption],
        operation_id="get_evaluation_models",
    )
    def get_evaluation_models():
        return handlers.get_evaluation_models()

    #####################################
    # - Endpoint: GET /api/profile-models
    #####################################
    # - Description: Compatibility alias, hidden from API docs. List supported providers and model
    #   IDs for resume-profile extraction.
    # - Output: HTTP 200. JSON array of ModelOption objects: value, label and model_id.
    @router.get(
        "/api/profile-models", response_model=list[ModelOption], include_in_schema=False
    )
    ####################################
    # - Endpoint: GET /api/models/resume
    ####################################
    # - Description: List supported providers and model IDs for resume-profile extraction.
    # - Output: HTTP 200. JSON array of ModelOption objects: value, label and model_id.
    @router.get(
        "/api/models/resume",
        response_model=list[ModelOption],
        operation_id="get_profile_models",
    )
    def get_profile_models():
        return handlers.get_profile_models()

    #############################
    # - Endpoint: GET /api/config
    #############################
    # - Description: Read public evaluation defaults and upload limits without exposing
    #   credentials.
    # - Output: HTTP 200. JSON configuration with evaluation mode, model choices, default provider
    #   and upload limits.
    @router.get("/api/config")
    def get_config():
        return handlers.get_config()

    ########################################
    # - Endpoint: GET /api/locations/suggest
    ########################################
    # - Description: Use query parameter q to look up worldwide city, region and country
    #   suggestions.
    # - Output: HTTP 200. JSON array of {label, value} suggestions; may be empty when no
    #   suggestions are available.
    @router.get("/api/locations/suggest")
    def suggest_locations(q: str = ""):
        "Return worldwide city, region, and country suggestions from Photon."
        return handlers.suggest_locations(q=q)

    return router
