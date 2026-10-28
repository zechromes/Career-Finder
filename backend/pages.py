"""Pages operations, separate from HTTP route declarations."""

from fastapi.responses import FileResponse, JSONResponse
from backend.paths import DIST_DIR


# Serve the built application entry point when a frontend build is available.
async def index():
    index_file = DIST_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={
                "message": "Vue frontend is not built. Run `npm install` and `npm run build` in frontend/."
            },
        )
    return FileResponse(index_file)


# Return the frontend entry point for supported client-side navigation.
async def spa_route():
    return await index()
