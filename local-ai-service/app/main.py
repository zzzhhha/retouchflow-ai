from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from . import __version__
from .ai_planner import Planner
from .config import load_ai_config
from .dashboard import router as dashboard_router
from .lightroom_params import (
    clamp_params,
    supported_aesthetics,
    supported_edit_levels,
    supported_scenes,
    supported_styles,
    to_lightroom_settings,
)
from .pixel_retouch import render_pixel_retouch
from .photoshop_bridge import (
    create_photoshop_job,
    get_next_photoshop_job,
    list_photoshop_jobs,
    mark_photoshop_job_complete,
    mark_photoshop_job_failed,
    photoshop_status,
    run_photoshop_job,
)
from .photoshop_retouch import prepare_photoshop_retouch
from .review import Reviewer
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApplyPlanRequest,
    ApplyPlanResponse,
    ExportReportRequest,
    HealthResponse,
    PixelRetouchRequest,
    PixelRetouchResponse,
    PhotoshopJobRequest,
    PhotoshopJobResponse,
    PhotoshopJobUpdateRequest,
    PhotoshopRetouchRequest,
    PhotoshopRetouchResponse,
    PhotoshopRunRequest,
    ReviewRequest,
    ReviewResponse,
)
from .storage import save_json


app = FastAPI(title="Lightroom Classic AI Retouch Service", version=__version__)
app.include_router(dashboard_router)
planner = Planner()
reviewer = Reviewer()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    config = load_ai_config()
    return HealthResponse(
        status="ok",
        version=__version__,
        supported_styles=supported_styles(),
        supported_scenes=supported_scenes(),
        supported_aesthetics=supported_aesthetics(),
        supported_edit_levels=supported_edit_levels(),
        ai_configured=config.configured,
    )


@app.post("/v1/batches/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    response = planner.analyze(request)
    save_json(request.batch_id, "analyze", response.model_dump())
    return response


@app.post("/v1/batches/apply-plan", response_model=ApplyPlanResponse)
def apply_plan(request: ApplyPlanRequest) -> ApplyPlanResponse:
    photos = [
        {
            "photo_id": photo.photo_id,
            "params": clamp_params(photo.params),
            "lightroom_settings": to_lightroom_settings(photo.params),
        }
        for photo in request.photos
    ]
    response = ApplyPlanResponse(batch_id=request.batch_id, photos=photos)
    save_json(request.batch_id, "apply-plan", response.model_dump())
    return response


@app.post("/v1/batches/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    response = reviewer.review(request)
    save_json(request.batch_id, f"review-pass-{request.pass_index}", response.model_dump())
    return response


@app.post("/v1/batches/export-report")
def export_report(request: ExportReportRequest) -> dict[str, str]:
    path = save_json(request.batch_id, "export-report", request.payload)
    return {"status": "ok", "path": str(path)}


@app.post("/v1/photos/pixel-retouch", response_model=PixelRetouchResponse)
def pixel_retouch(request: PixelRetouchRequest) -> PixelRetouchResponse:
    result = render_pixel_retouch(
        request.input_path,
        request.output_path,
        scene=request.scene,
        aesthetic=request.aesthetic,
        operations=request.operations,
        strength=request.strength,
        user_suggestion=request.user_suggestion,
    )
    result["photo_id"] = request.photo_id
    if request.batch_id:
        save_json(request.batch_id, f"pixel-retouch-{_safe_json_name(request.photo_id or 'photo')}", result)
    return PixelRetouchResponse(**result)


@app.post("/v1/photos/photoshop-retouch", response_model=PhotoshopRetouchResponse)
def photoshop_retouch(request: PhotoshopRetouchRequest) -> PhotoshopRetouchResponse:
    result = prepare_photoshop_retouch(request)
    result["job"] = _photoshop_job_response(result["job"])
    if request.batch_id:
        save_json(request.batch_id, f"photoshop-retouch-{_safe_json_name(request.photo_id or 'photo')}", _model_safe(result))
    return PhotoshopRetouchResponse(**result)


@app.get("/v1/photoshop/status")
def photoshop_bridge_status() -> dict[str, Any]:
    return photoshop_status()


@app.post("/v1/photoshop/jobs", response_model=PhotoshopJobResponse)
def photoshop_job_create(request: PhotoshopJobRequest) -> PhotoshopJobResponse:
    job = create_photoshop_job(request)
    return _photoshop_job_response(job)


@app.get("/v1/photoshop/jobs/next")
def photoshop_job_next(batch_id: str | None = None) -> dict[str, Any]:
    job = get_next_photoshop_job(batch_id=batch_id)
    return job or {"status": "empty", "message": "No queued Photoshop jobs."}


@app.get("/v1/photoshop/jobs")
def photoshop_job_list(batch_id: str) -> list[dict[str, Any]]:
    return list_photoshop_jobs(batch_id)


@app.post("/v1/photoshop/jobs/{batch_id}/{job_id}/run", response_model=PhotoshopJobResponse)
def photoshop_job_run(batch_id: str, job_id: str, request: PhotoshopRunRequest) -> PhotoshopJobResponse:
    job = run_photoshop_job(
        job_id,
        batch_id,
        photoshop_exe=request.photoshop_exe or None,
        wait_seconds=request.wait_seconds,
    )
    return _photoshop_job_response(job)


@app.post("/v1/photoshop/jobs/{batch_id}/{job_id}/complete", response_model=PhotoshopJobResponse)
def photoshop_job_complete(batch_id: str, job_id: str, request: PhotoshopJobUpdateRequest) -> PhotoshopJobResponse:
    job = mark_photoshop_job_complete(job_id, batch_id, request.model_dump())
    return _photoshop_job_response(job)


@app.post("/v1/photoshop/jobs/{batch_id}/{job_id}/failed", response_model=PhotoshopJobResponse)
def photoshop_job_failed(batch_id: str, job_id: str, request: PhotoshopJobUpdateRequest) -> PhotoshopJobResponse:
    job = mark_photoshop_job_failed(job_id, batch_id, request.message or "Photoshop job failed.", request.model_dump())
    return _photoshop_job_response(job)


def _safe_json_name(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value))
    clean = clean.strip("_")
    if not clean:
        clean = "photo"
    return clean[-80:]


def _photoshop_job_response(job: dict[str, Any]) -> PhotoshopJobResponse:
    return PhotoshopJobResponse(
        status=str(job.get("status") or ""),
        job_id=str(job.get("job_id") or ""),
        batch_id=str(job.get("batch_id") or ""),
        photo_id=str(job.get("photo_id") or ""),
        input_path=str(job.get("input_path") or ""),
        output_path=str(job.get("output_path") or ""),
        psd_path=str(job.get("psd_path") or ""),
        job_path=str(job.get("job_path") or ""),
        script_path=str(job.get("script_path") or ""),
        photoshop_exe=str(job.get("photoshop_exe") or photoshop_status().get("photoshop_exe") or ""),
        message=str(job.get("message") or ""),
        quality_mode=str(job.get("quality_mode") or "standard"),
        operation_count=len(job.get("operations", [])) if isinstance(job.get("operations"), list) else 0,
        mask_count=len(job.get("mask_assets", [])) if isinstance(job.get("mask_assets"), list) else 0,
    )


def _model_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _model_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_model_safe(item) for item in value]
    return value
