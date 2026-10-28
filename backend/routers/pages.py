"""HTTP routes for pages; business logic stays in the injected handlers."""

from fastapi import APIRouter


def build_router(handlers):
    """Bind request adapters without importing the application or its mutable state."""
    router = APIRouter()

    ###################
    # - Endpoint: GET /
    ###################
    # - Description: Serve the built Vue application entry page.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/")
    async def index():
        return await handlers.index()

    ###############################
    # - Endpoint: GET /run/{run_id}
    ###############################
    # - Description: Serve the Vue application for a direct page visit or refresh; Vue selects the
    #   view from the URL.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/run/{run_id}")

    #######################################
    # - Endpoint: GET /run/{run_id}/results
    #######################################
    # - Description: Serve the Vue application for a direct page visit or refresh; Vue selects the
    #   view from the URL.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/run/{run_id}/results")

    ###################################
    # - Endpoint: GET /run/{run_id}/job
    ###################################
    # - Description: Serve the Vue application for a direct page visit or refresh; Vue selects the
    #   view from the URL.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/run/{run_id}/job")

    ###########################
    # - Endpoint: GET /profiles
    ###########################
    # - Description: Serve the Vue application for a direct page visit or refresh; Vue selects the
    #   view from the URL.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/profiles")

    ##########################
    # - Endpoint: GET /privacy
    ##########################
    # - Description: Serve the Vue application for a direct page visit or refresh; Vue selects the
    #   view from the URL.
    # - Output: HTTP 200. HTML frontend entry file; HTTP 503 with a JSON message if the frontend
    #   is not built.
    @router.get("/eval/datasets/{dataset_id}")
    @router.get("/eval")
    @router.get("/privacy")
    async def spa_route():
        return await handlers.spa_route()

    return router
