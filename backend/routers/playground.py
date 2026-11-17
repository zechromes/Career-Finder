"""Run one pipeline stage on its own for inspection; nothing is saved."""

import io
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.evaluation import upload_check
from backend.profiles import extraction, upload
from backend.schemas.contracts import Preferences
from backend.schemas.playground import (
    IngestionPlayground,
    RetrievalPlayground,
    RetrievalRequest,
    UploadPlayground,
)
from backend.search import collection, ingestion_log, retrieval
from backend.search.embedding_text import profile_embedding_text
from backend.search.ranking import retrieval_queries, retrieval_query_weights

router = APIRouter(prefix="/api/playground", tags=["Playground"])


@router.post("/upload", response_model=UploadPlayground)
async def upload_stage(resume: UploadFile = File(...)):
    """Read a PDF into a profile exactly as an upload does, then check it. One live model call."""
    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF resumes are supported.")
    data = await upload.read_resume(resume)
    try:
        text = await run_in_threadpool(
            extraction.extract_text_from_resume, io.BytesIO(data)
        )
        if not text:
            raise ValueError("No text could be extracted from the uploaded PDF.")
        profile = await run_in_threadpool(upload.classify_and_extract_resume, text)
    except upload.ResumeVerificationError as exc:
        raise HTTPException(503, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"profile": profile, "check": upload_check.check(profile)}


@router.post("/ingestion", response_model=IngestionPlayground)
def ingestion_stage(body: Preferences):
    """Collect jobs live from the boards, bypassing the cache. Nothing reaches a search.

    shortcut: runs inside the request (up to the collection time limit) with no
    cancel; move to a background job if runs need stopping.
    """
    # Like a real search, no location means a worldwide search.
    locations = body.locations or ["Worldwide"]
    log = ingestion_log.IngestionLog()
    messages, status = [], [""]
    with ingestion_log.recording(log):
        jobs = collection.fetch_job_vacancies(
            body.queries,
            locations,
            body.platforms,
            adaptive=True,
            remote=body.work_type == "remote",
            posted_days_old=body.posted_days_old,
            on_error=lambda message: messages.append(str(message)),
            on_status=lambda message: status.__setitem__(0, str(message)),
            force_refresh=True,
            search_filters=dict(
                exclusions=body.exclusions,
                work_type=body.work_type,
                seniority=body.seniority,
            ),
        )
    record = log.to_dict(len(jobs))
    return dict(
        status=status[0],
        messages=messages,
        collected=record["collected"],
        counts=record["counts"],
        jobs=[
            dict(
                title=str(job.get("title", "")),
                company=str(job.get("company", "")),
                location=str(job.get("location", "")),
                board=str(job.get("source_platform", "")),
                posted_at=str(job.get("posted_at", "")),
                url=str(job.get("url", "")),
                description_chars=len(job.get("description") or ""),
                description=str(job.get("description") or ""),
            )
            for job in jobs
        ],
        dropped=record["dropped"],
    )


@router.post("/retrieval", response_model=RetrievalPlayground)
def retrieval_stage(body: RetrievalRequest):
    """Rank given jobs against a profile as a real search does, in a throwaway index.

    Live OpenAI embedding calls; vectors come from the shared embedding cache when present.
    """
    from backend.evaluation.candidate_fit import posting_exceeds_candidate_level

    profile = body.profile.model_dump()
    context = profile_embedding_text(profile)
    queries = retrieval_queries(profile, body.queries, builder=body.query_builder)
    weights = retrieval_query_weights(profile, body.queries, builder=body.query_builder)
    jobs = [
        dict(job.model_dump(), source_platform=job.board)
        for job in body.jobs
        if job.description.strip()
    ]
    if not jobs:
        raise HTTPException(422, "None of the jobs has a description to rank.")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        collection.vectorize_jobs_to_db(jobs, persist_dir=directory)
        documents = retrieval.retrieve_relevant_jobs(
            context,
            persist_dir=directory,
            top_k=body.top_k,
            queries=queries,
            candidate_profile=profile if body.seniority == "auto" else None,
            query_weights=weights,
        )
    return dict(
        queries=[dict(text=query, weight=round(weights.get(query, 1.0), 3)) for query in queries],
        ranked=[
            dict(
                rank=position,
                title=doc.metadata.get("title", ""),
                company=doc.metadata.get("company", ""),
                location=doc.metadata.get("location", ""),
                board=doc.metadata.get("source", ""),
                url=doc.metadata.get("url", ""),
                above_level=body.seniority == "auto"
                and bool(
                    posting_exceeds_candidate_level(
                        doc.metadata.get("title", ""),
                        doc.metadata.get("job_description") or doc.page_content,
                        context,
                        profile,
                    )
                ),
            )
            for position, doc in enumerate(documents, 1)
        ],
        total_jobs=len(jobs),
    )
