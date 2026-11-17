"""HTTP routes for searches; business logic stays in the injected handlers."""

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import StreamingResponse
from typing import Literal
from backend import runs_api, configuration
from backend.evaluation import service as evaluation_service
from backend.schemas.contracts import (
    FindMoreRequest,
    ProfileConfirmation,
    RunSnapshot,
    RunCreated,
)


def build_router(handlers):
    """Bind request adapters without importing the application or its mutable state."""
    router = APIRouter()
    from backend.schemas.contracts import JobActionUpdate, JobActions

    @router.get("/api/searches/{run_id}/actions", response_model=JobActions)
    def get_job_actions(run_id: str):
        return runs_api.job_actions(run_id)

    @router.put("/api/searches/{run_id}/actions", response_model=JobActions)
    def update_job_action(run_id: str, body: JobActionUpdate):
        return runs_api.job_actions(run_id, body)

    from backend.schemas.tailored_resume import TailoredResume, TailoredResumeRequest

    # One live Claude call; the resume is also saved with the job in this search's results.
    @router.post("/api/searches/{run_id}/tailored-resume", response_model=TailoredResume)
    def create_tailored_resume(run_id: str, body: TailoredResumeRequest):
        return runs_api.tailored_resume(run_id, body.key)

    ############################################
    # - Endpoint: POST /api/runs/{run_id}/search
    ############################################
    # - Description: Compatibility alias, hidden from API docs. Start job collection and
    #   evaluation from form inputs; append when results already exist.
    # - Output: HTTP 202. JSON {id}; append mode also returns runId. Work continues in the
    #   background.
    @router.post(
        "/api/runs/{run_id}/search",
        status_code=status.HTTP_202_ACCEPTED,
        include_in_schema=False,
    )
    ###################################################
    # - Endpoint: POST /api/searches/{run_id}/find-jobs
    ###################################################
    # - Description: Start job collection and evaluation from form inputs; append when results
    #   already exist.
    # - Output: HTTP 202. JSON {id}; append mode also returns runId. Work continues in the
    #   background.
    @router.post(
        "/api/searches/{run_id}/find-jobs",
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="start_job_search",
    )
    async def start_job_search(
        run_id: str,
        queries: str = Form(...),
        locations: str = Form(""),
        platforms: str = Form("linkedin,indeed"),
        remote: bool = Form(False),
        posted_days_old: int = Form(30),
        top_k: int = Form(15),
        evaluation_model: Literal["gemini", "claude", "gpt"] = Form(
            configuration.DEFAULT_EVALUATION_PROVIDER
        ),
    ):
        "Start steps 2 and 3 after the user confirms the profile search inputs."
        return await handlers.start_job_search(
            run_id=run_id,
            queries=queries,
            locations=locations,
            platforms=platforms,
            remote=remote,
            posted_days_old=posted_days_old,
            top_k=top_k,
            evaluation_model=evaluation_model,
        )

    ###################################################
    # - Endpoint: POST /api/searches/{run_id}/find-more
    ###################################################
    # - Description: Use updated preferences to append unique jobs while retaining the existing
    #   profile and results.
    # - Output: HTTP 202. JSON {id, runId}; additional collection and evaluation continue in the
    #   background.
    @router.post(
        "/api/searches/{run_id}/find-more",
        status_code=202,
        response_model=RunCreated,
        operation_id="find_more_jobs",
    )
    async def find_more_jobs(run_id: str, body: FindMoreRequest):
        "Append new postings using the existing profile and edited search preferences."
        return await handlers.find_more_jobs(run_id=run_id, body=body)

    @router.post(
        "/api/searches/{run_id}/retry-scraping",
        status_code=202,
        response_model=RunCreated,
        operation_id="retry_scraping",
    )
    async def retry_scraping(run_id: str):
        """Retry failed boards with confirmed preferences, retaining existing results."""
        return await handlers.retry_scraping(run_id)

    ####################################
    # - Endpoint: GET /api/runs/{run_id}
    ####################################
    # - Description: Compatibility alias, hidden from API docs. Read the current workspace without
    #   starting a search or evaluation.
    # - Output: HTTP 200. RunSnapshot JSON containing profile, preferences, progress, results,
    #   errors and worker status.
    @router.get(
        "/api/runs/{run_id}", response_model=RunSnapshot, include_in_schema=False
    )
    ########################################
    # - Endpoint: GET /api/searches/{run_id}
    ########################################
    # - Description: Read the current workspace without starting a search or evaluation.
    # - Output: HTTP 200. RunSnapshot JSON containing profile, preferences, progress, results,
    #   errors and worker status.
    @router.get(
        "/api/searches/{run_id}", response_model=RunSnapshot, operation_id="get_search"
    )
    async def get_search(run_id: str):
        return await runs_api.get_search(run_id=run_id)

    #######################################
    # - Endpoint: DELETE /api/runs/{run_id}
    #######################################
    # - Description: Compatibility alias, hidden from API docs. Delete the workspace; defer file
    #   removal while its worker is active. Saved profiles remain.
    # - Output: HTTP 200. JSON {deleted: boolean, deletion_pending: boolean}.
    @router.delete("/api/runs/{run_id}", include_in_schema=False)

    ###########################################
    # - Endpoint: DELETE /api/searches/{run_id}
    ###########################################
    # - Description: Delete the workspace; defer file removal while its worker is active. Saved
    #   profiles remain.
    # - Output: HTTP 200. JSON {deleted: boolean, deletion_pending: boolean}.
    @router.delete("/api/searches/{run_id}", operation_id="delete_search")
    async def delete_search(run_id: str):
        "Flush the active run and all generated files when starting over."
        return await runs_api.delete_search(run_id=run_id)

    #########################################################
    # - Endpoint: GET /api/runs/{run_id}/download/{file_name}
    #########################################################
    # - Description: Compatibility alias, hidden from API docs. Download an allowlisted
    #   retrieved_jobs.csv or relevant_jobs.xlsx file for the workspace.
    # - Output: HTTP 200. CSV or Excel file attachment; 404 if the workspace or requested export
    #   is unavailable.
    @router.get("/api/runs/{run_id}/download/{file_name}", include_in_schema=False)

    ############################################################
    # - Endpoint: GET /api/searches/{run_id}/exports/{file_name}
    ############################################################
    # - Description: Download an allowlisted retrieved_jobs.csv or relevant_jobs.xlsx file for the
    #   workspace.
    # - Output: HTTP 200. CSV or Excel file attachment; 404 if the workspace or requested export
    #   is unavailable.
    @router.get(
        "/api/searches/{run_id}/exports/{file_name}",
        operation_id="download_search_export",
    )
    async def download_search_export(run_id: str, file_name: str):
        return await runs_api.download_search_export(run_id=run_id, file_name=file_name)

    ############################################
    # - Endpoint: PUT /api/runs/{run_id}/profile
    ############################################
    # - Description: Compatibility alias, hidden from API docs. Confirm profile and search
    #   preferences, then start collection; existing assessments use append mode.
    # - Output: HTTP 202. JSON {id, runId}; collection and evaluation continue in the background.
    @router.put(
        "/api/runs/{run_id}/profile",
        status_code=202,
        response_model=RunCreated,
        include_in_schema=False,
    )

    ########################################################
    # - Endpoint: PUT /api/searches/{run_id}/confirm-profile
    ########################################################
    # - Description: Confirm profile and search preferences, then start collection; existing
    #   assessments use append mode.
    # - Output: HTTP 202. JSON {id, runId}; collection and evaluation continue in the background.
    @router.put(
        "/api/searches/{run_id}/confirm-profile",
        status_code=202,
        response_model=RunCreated,
        operation_id="confirm_search_profile",
    )
    async def confirm_search_profile(run_id: str, body: ProfileConfirmation):
        return await handlers.confirm_search_profile(run_id=run_id, body=body)

    ############################################
    # - Endpoint: POST /api/runs/{run_id}/cancel
    ############################################
    # - Description: Compatibility alias, hidden from API docs. Request cooperative cancellation
    #   while retaining results already published.
    # - Output: HTTP 200. Current RunSnapshot JSON; in-flight worker activity may still be
    #   reported.
    @router.post("/api/runs/{run_id}/cancel", include_in_schema=False)

    ################################################
    # - Endpoint: POST /api/searches/{run_id}/cancel
    ################################################
    # - Description: Request cooperative cancellation while retaining results already published.
    # - Output: HTTP 200. Current RunSnapshot JSON; in-flight worker activity may still be
    #   reported.
    @router.post("/api/searches/{run_id}/cancel", operation_id="cancel_search")
    async def cancel_search(run_id: str):
        return await runs_api.cancel_search(run_id=run_id)

    ###########################################
    # - Endpoint: GET /api/runs/{run_id}/events
    ###########################################
    # - Description: Compatibility alias, hidden from API docs. Subscribe to workspace progress
    #   and result snapshots until completion or disconnection.
    # - Output: HTTP 200. text/event-stream response containing server-sent events, not a single
    #   JSON document.
    @router.get(
        "/api/runs/{run_id}/events",
        response_class=StreamingResponse,
        responses={
            200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}
        },
        include_in_schema=False,
    )

    #################################################
    # - Endpoint: GET /api/searches/{run_id}/progress
    #################################################
    # - Description: Subscribe to workspace progress and result snapshots until completion or
    #   disconnection.
    # - Output: HTTP 200. text/event-stream response containing server-sent events, not a single
    #   JSON document.
    @router.get(
        "/api/searches/{run_id}/progress",
        response_class=StreamingResponse,
        responses={
            200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}
        },
        operation_id="stream_search_progress",
    )
    async def stream_search_progress(run_id: str, request: Request):
        return await runs_api.stream_search_progress(run_id=run_id, request=request)

    ######################################################
    # - Endpoint: POST /api/runs/{run_id}/retry-evaluation
    ######################################################
    # - Description: Compatibility alias, hidden from API docs. Retry checkpointed provider
    #   failures without scraping again or repeating successful assessments.
    # - Output: HTTP 202. JSON {id, runId}; targeted evaluation retries continue in the
    #   background.
    @router.post(
        "/api/runs/{run_id}/retry-evaluation", status_code=202, include_in_schema=False
    )

    ###########################################################
    # - Endpoint: POST /api/searches/{run_id}/retry-evaluations
    ###########################################################
    # - Description: Retry checkpointed provider failures without scraping again or repeating
    #   successful assessments.
    # - Output: HTTP 202. JSON {id, runId}; targeted evaluation retries continue in the
    #   background.
    @router.post(
        "/api/searches/{run_id}/retry-evaluations",
        status_code=202,
        operation_id="retry_search_evaluations",
    )
    async def retry_search_evaluations(run_id: str):
        return await evaluation_service.retry_search_evaluations(run_id=run_id)

    return router
