"""Assemble the FastAPI application, middleware, routers, and frontend assets."""

# Framework tools for creating the API, allowing frontend requests, and serving assets.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
# Shared paths, run storage, and the function that connects feature routers to the API.
from backend.paths import DIST_DIR
from backend import runs, api_keys
from backend.routers import register_routers

# Ensure the run folder exists and restore saved search state when the API starts.
runs.RUNS_DIR.mkdir(exist_ok=True)
runs.load_persisted_runs()
# Keys saved on the Settings page take priority over .env.
api_keys.load()

# Create the application; this title and version also appear in the API documentation.
app = FastAPI(title="Career Finder Job Search API", version="1.0.0")

# Allow the local Vue development server to call this API from a different port.
# Browsers use these CORS settings to decide which cross-origin requests are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# Before handling each request, clean up expired runs and enforce request limits.
# The middleware passes accepted requests on to the matching endpoint.
app.middleware("http")(runs.limits)

# Register the endpoint groups and connect them to their feature handlers.
# Upload, search, evaluation, and profile processing live in their own modules.
register_routers(app)

# Serve the built frontend's JavaScript and CSS when its assets are available.
if DIST_DIR.exists() and (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

# Start the local API server when this module is executed directly.
# Importing it through a launcher only creates the app; the launcher starts the server.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=5000, reload=False)
