"""Read frozen evaluation inputs and save human judgments separately."""

from fastapi import APIRouter
from backend.evaluation import review_datasets as service
from backend.evaluation import replay as replay_service
from backend.schemas.review_datasets import (
    CreateReviewDataset,
    ReviewBundle,
    ReviewDatasetSummary,
    SaveReview,
    ReviewState,
    ReviewMetrics,
    ReplayResult,
)

router = APIRouter(prefix="/api/review-datasets", tags=["Evaluation datasets"])


@router.get("", response_model=list[ReviewDatasetSummary])
def list_datasets():
    return service.summaries()


@router.post("", response_model=ReviewBundle, status_code=201)
def create_dataset(body: CreateReviewDataset):
    return service.create(body.source_id)


@router.get("/{identifier}", response_model=ReviewBundle)
def get_dataset(identifier: str):
    return service.read(identifier)


@router.delete("/{identifier}")
def delete_dataset(identifier: str):
    return service.delete(identifier)


@router.put("/{identifier}/jobs/{job_id}", response_model=ReviewState)
def save_review(identifier: str, job_id: str, body: SaveReview):
    return service.save(identifier, job_id, body)


@router.get("/{identifier}/metrics", response_model=ReviewMetrics)
def metrics(identifier: str):
    return service.measure(identifier)


@router.post("/{identifier}/replay", response_model=ReplayResult)
def replay(identifier: str):
    return replay_service.replay(identifier)
