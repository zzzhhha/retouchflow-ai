from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PhotoMetadata(BaseModel):
    camera: str | None = None
    lens: str | None = None
    iso: int | None = None
    aperture: float | None = None
    shutter: str | None = None
    focal_length: float | None = None


class AnalyzePhoto(BaseModel):
    photo_id: str
    file_name: str
    preview_path: str
    metadata: PhotoMetadata = Field(default_factory=PhotoMetadata)


class AnalyzeRequest(BaseModel):
    batch_id: str
    style: str = "natural_portrait"
    scene: str = "auto"
    aesthetic: str = "natural"
    edit_level: str = "basic"
    user_suggestion: str = ""
    photos: list[AnalyzePhoto]


class GroupStyle(BaseModel):
    style: str
    scene: str
    aesthetic: str = "natural"
    edit_level: str = "basic"
    skin_tone_target: str
    contrast_level: str
    base_params: dict[str, float | int]


class PhotoPlan(BaseModel):
    photo_id: str
    file_name: str
    detected_scene: str = "auto"
    ai_source: str = "rules"
    ai_notes: list[str] = Field(default_factory=list)
    params: dict[str, float | int]
    lightroom_settings: dict[str, Any]
    metrics: dict[str, Any]
    local_analysis: dict[str, Any] = Field(default_factory=dict)
    crop_suggestion: dict[str, Any] = Field(default_factory=dict)
    advanced_plan: dict[str, Any] = Field(default_factory=dict)
    advanced_suggestions: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    batch_id: str
    style: str
    scene: str = "auto"
    aesthetic: str = "natural"
    edit_level: str = "basic"
    user_suggestion: str = ""
    ai_status: dict[str, Any] = Field(default_factory=dict)
    group_style: GroupStyle
    photos: list[PhotoPlan]


class ApplyPlanPhoto(BaseModel):
    photo_id: str
    params: dict[str, float | int]


class ApplyPlanRequest(BaseModel):
    batch_id: str
    photos: list[ApplyPlanPhoto]


class ApplyPlanResponse(BaseModel):
    batch_id: str
    photos: list[dict[str, Any]]


class ReviewPhoto(BaseModel):
    photo_id: str
    before_path: str
    after_path: str
    params: dict[str, float | int] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    batch_id: str
    style: str = "natural_portrait"
    scene: str = "auto"
    aesthetic: str = "natural"
    edit_level: str = "basic"
    user_suggestion: str = ""
    pass_index: int = 1
    photos: list[ReviewPhoto]


class ReviewResult(BaseModel):
    photo_id: str
    passed: bool
    score: int
    issues: list[str]
    deltas: dict[str, float | int]
    metrics: dict[str, Any]
    ai_source: str = "rules"
    ai_notes: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    batch_id: str
    passed: bool
    score: int
    photos: list[ReviewResult]
    ai_status: dict[str, Any] = Field(default_factory=dict)


class ExportReportRequest(BaseModel):
    batch_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PixelRetouchRequest(BaseModel):
    photo_id: str = ""
    input_path: str
    output_path: str
    scene: str = "auto"
    aesthetic: str = "natural"
    operations: list[str] = Field(default_factory=list)
    strength: float | None = None
    batch_id: str = ""
    user_suggestion: str = ""


class PixelRetouchResponse(BaseModel):
    status: str
    photo_id: str = ""
    input_path: str
    output_path: str
    scene: str
    aesthetic: str
    operations_requested: list[str]
    operations_applied: list[dict[str, Any]]
    local_analysis: dict[str, Any]
    quality: dict[str, Any] = Field(default_factory=dict)


class PhotoshopJobRequest(BaseModel):
    batch_id: str = "manual-photoshop"
    photo_id: str = ""
    input_path: str
    output_path: str = ""
    psd_path: str = ""
    scene: str = "auto"
    aesthetic: str = "natural"
    operations: list[dict[str, Any]] = Field(default_factory=list)
    mask_assets: list[dict[str, Any]] = Field(default_factory=list)
    quality_mode: str = "standard"
    strength: float | None = None
    user_suggestion: str = ""


class PhotoshopJobResponse(BaseModel):
    status: str
    job_id: str
    batch_id: str
    photo_id: str = ""
    input_path: str
    output_path: str
    psd_path: str
    job_path: str
    script_path: str = ""
    photoshop_exe: str = ""
    message: str = ""
    quality_mode: str = "standard"
    operation_count: int = 0
    mask_count: int = 0


class PhotoshopRetouchRequest(BaseModel):
    batch_id: str = "manual-photoshop"
    photo_id: str = ""
    input_path: str
    output_path: str = ""
    psd_path: str = ""
    scene: str = "auto"
    aesthetic: str = "natural"
    operations: list[str] = Field(default_factory=list)
    strength: float | None = None
    user_suggestion: str = ""
    run: bool = False
    wait_seconds: int = 5
    photoshop_exe: str = ""


class PhotoshopRetouchResponse(BaseModel):
    status: str
    photo_id: str = ""
    input_path: str
    output_path: str
    psd_path: str
    scene: str
    aesthetic: str
    operations_requested: list[str]
    operations_planned: list[dict[str, Any]]
    mask_assets: list[dict[str, Any]] = Field(default_factory=list)
    local_analysis: dict[str, Any]
    job: PhotoshopJobResponse
    quality: dict[str, Any] = Field(default_factory=dict)


class PhotoshopJobUpdateRequest(BaseModel):
    output_path: str = ""
    psd_path: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class PhotoshopRunRequest(BaseModel):
    wait_seconds: int = 5
    photoshop_exe: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    supported_styles: list[str]
    supported_scenes: list[str] = Field(default_factory=list)
    supported_aesthetics: list[str] = Field(default_factory=list)
    supported_edit_levels: list[str] = Field(default_factory=list)
    ai_configured: bool = False
