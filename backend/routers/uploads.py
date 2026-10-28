"""HTTP routes for uploads; business logic stays in the injected handlers."""

from fastapi import APIRouter, File, Form, UploadFile, status
from backend.schemas.contracts import RunCreated


def build_router(handlers):
    """Bind request adapters without importing the application or its mutable state."""
    router = APIRouter()

    ############################
    # - Endpoint: POST /api/runs
    ############################
    # - Description: Compatibility alias, hidden from API docs. Validate and save the PDF, then
    #   wait for profile extraction before returning.
    # - Output: HTTP 202. JSON {id, runId}; fetch the workspace snapshot for the profile or
    #   extraction error.
    @router.post(
        "/api/runs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunCreated,
        include_in_schema=False,
    )

    ################################
    # - Endpoint: POST /api/searches
    ################################
    # - Description: Compatibility alias, hidden from API docs. Validate and save the PDF, then
    #   wait for profile extraction before returning.
    # - Output: HTTP 202. JSON {id, runId}; fetch the workspace snapshot for the profile or
    #   extraction error.
    @router.post(
        "/api/searches",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunCreated,
        include_in_schema=False,
    )

    ######################################
    # - Endpoint: POST /api/resumes/upload
    ######################################
    # - Description: Validate and save the PDF, then wait for profile extraction before returning.
    # - Output: HTTP 201. JSON {id, runId}; fetch the workspace snapshot for the profile or
    #   extraction error.
    @router.post(
        "/api/resumes/upload",
        status_code=status.HTTP_201_CREATED,
        response_model=RunCreated,
        operation_id="upload_resume",
        summary="Upload resume",
        responses={
            422: {
                "description": "Invalid PDF, unreadable text, or document not identified as a resume/CV."
            },
            503: {
                "description": "The resume/CV detection service is unavailable or returned an invalid result."
            },
        },
        tags=["Resume upload"],
        response_description="The workspace ID after extraction finishes. Read its snapshot for the profile or extraction error.",
    )
    async def upload_resume(
        resume: UploadFile = File(
            ..., description="Your resume as a PDF file, up to 5 MB."
        ),
        model: str = Form(
            "openai", description="Resume-reading provider from GET /api/models/resume."
        ),
    ):
        """
        Upload a PDF resume and start reading its candidate profile.

        Verifies the PDF is a resume/CV before creating a workspace, then waits for profile extraction.
        There is no detached extraction task. Read `GET /api/searches/{run_id}` after
        this response for the extracted profile or recorded extraction error.

        Job searching starts only after you review and confirm your profile and search
        preferences using `PUT /api/searches/{run_id}/confirm-profile`.
        """
        return await handlers.upload_resume(resume=resume, model=model)

    return router
