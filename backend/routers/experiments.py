"""Experiment routes are separate from production search lifecycle."""

from fastapi import APIRouter
from backend.evaluation import experiments
from backend.schemas.experiments import (
    ExperimentOptions,
    ExperimentSource,
    ExperimentDataset,
    ExperimentRequest,
    ExperimentResult,
)

router = APIRouter(prefix="/api/experiments", tags=["Experiments"])


@router.get("/options", response_model=ExperimentOptions)
def options():
    return experiments.options()


@router.get("/sources", response_model=list[ExperimentSource])
def sources():
    return experiments.sources()


@router.get("/sources/{source_id}", response_model=ExperimentDataset)
def dataset(source_id: str):
    # Validate before any filesystem access, including direct requests.
    if len(source_id) != 32 or any(c not in "0123456789abcdef" for c in source_id):
        from fastapi import HTTPException

        raise HTTPException(404, "Workspace not found.")
    return experiments.dataset(source_id)[0]


@router.post("", response_model=ExperimentResult, status_code=202)
def start(body: ExperimentRequest):
    return experiments.start(body)


@router.get("/{experiment_id}", response_model=ExperimentResult)
def result(experiment_id: str):
    return experiments.get(experiment_id)


@router.post("/{experiment_id}/cancel", response_model=ExperimentResult)
def cancel(experiment_id: str):
    return experiments.cancel(experiment_id)
