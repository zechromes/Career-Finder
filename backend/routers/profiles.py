"""Saved-profile HTTP routes, separate from disk persistence functions."""

from fastapi import APIRouter


def build_router(storage):
    # Import schemas only after storage has finished defining its functions.
    from backend.schemas.saved_profiles import SavedProfile, SavedProfileInput

    router = APIRouter(prefix="/api/profiles", tags=["Profiles"])

    ###############################
    # - Endpoint: GET /api/profiles
    ###############################
    # - Description: List independent saved profiles, ordered by most recently updated first.
    # - Output: HTTP 200. JSON array of SavedProfile objects, including metadata, profile,
    #   preferences and attachment availability.
    @router.get("", response_model=list[SavedProfile], operation_id="list_profiles")
    def list_profiles():
        return storage.list_profiles()

    ################################
    # - Endpoint: POST /api/profiles
    ################################
    # - Description: Save a profile and copy the source resume PDF when a source run is supplied.
    # - Output: HTTP 201. SavedProfile JSON with its new ID, timestamps and resume_available flag.
    @router.post(
        "", response_model=SavedProfile, status_code=201, operation_id="create_profile"
    )
    def create_profile(body: SavedProfileInput):
        return storage.create_profile(body=body)

    ############################################
    # - Endpoint: PUT /api/profiles/{profile_id}
    ############################################
    # - Description: Update a saved profile and preferences while retaining its original
    #   attachment and creation date.
    # - Output: HTTP 200. Updated SavedProfile JSON.
    @router.put(
        "/{profile_id}", response_model=SavedProfile, operation_id="update_profile"
    )
    def update_profile(profile_id: str, body: SavedProfileInput):
        return storage.update_profile(profile_id=profile_id, body=body)

    ###############################################
    # - Endpoint: DELETE /api/profiles/{profile_id}
    ###############################################
    # - Description: Remove the saved profile and its attachment without deleting its search
    #   workspaces.
    # - Output: HTTP 200. JSON {deleted: true}; 404 if the saved profile does not exist.
    @router.delete("/{profile_id}", operation_id="delete_profile")
    def delete_profile(profile_id: str):
        return storage.delete_profile(profile_id=profile_id)

    ###################################################
    # - Endpoint: GET /api/profiles/{profile_id}/resume
    ###################################################
    # - Description: Download the saved profile’s independent PDF attachment.
    # - Output: HTTP 200. PDF attachment named resume.pdf; 404 if the profile or attachment is
    #   unavailable.
    @router.get("/{profile_id}/resume", operation_id="download_resume")
    def download_resume(profile_id: str):
        return storage.download_resume(profile_id=profile_id)

    return router
