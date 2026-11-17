"""Repository paths shared by the API and pipeline; independent of working directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
# Preserve existing run URLs and data after the code reorganization.
RUNS_DIR = FRONTEND_DIR / "runs"
DIST_DIR = FRONTEND_DIR / "dist"
JOB_EMBEDDING_CACHE_DIR = PROJECT_ROOT / ".cache" / "job_embeddings"

JOB_COLLECTION_CACHE_DIR = PROJECT_ROOT / ".cache" / "job_collections"
JOB_INDEX_DIR = PROJECT_ROOT / ".cache" / "job_index"
LINKEDIN_DESCRIPTION_CACHE_DIR = PROJECT_ROOT / ".cache" / "linkedin_descriptions"

JOB_DESCRIPTION_CACHE_DIR = PROJECT_ROOT / ".cache" / "job_descriptions"

JOB_REQUIREMENT_CACHE_DIR = PROJECT_ROOT / ".cache" / "job_requirements"
# Labeled datasets: the earlier review datasets and the ones built from job actions.
REVIEW_DATASETS_DIR = PROJECT_ROOT / "data" / "evaluation_datasets"
# Provider API keys saved from the Settings page; private like the rest of data/.
API_KEYS_FILE = PROJECT_ROOT / "data" / "api_keys.json"
# Generated HyDE job ads; derived from resumes, so private like the other caches.
HYDE_QUERY_CACHE_DIR = PROJECT_ROOT / ".cache" / "hyde_queries"

