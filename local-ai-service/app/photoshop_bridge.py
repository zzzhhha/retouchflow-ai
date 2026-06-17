from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .photoshop_actions import apply_photoshop_action_config, photoshop_action_status
from .schemas import PhotoshopJobRequest
from .storage import append_event, batch_dir, run_root, safe_batch_id
from .user_intent import clean_user_suggestion


DEFAULT_JOB_TIMEOUT_SECONDS = 180


def default_photoshop_exe() -> Path:
    env_path = os.getenv("AI_RETOUCH_PHOTOSHOP_EXE", "").strip()
    if env_path:
        return Path(env_path)
    for candidate in _photoshop_exe_candidates():
        if candidate.exists():
            return candidate
    candidates = _photoshop_exe_candidates()
    return candidates[0] if candidates else Path("Photoshop.exe")


def _photoshop_exe_candidates() -> list[Path]:
    candidates: list[Path] = []
    for root in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)")):
        if not root:
            continue
        for year in ("2026", "2025", "2024", "2023"):
            candidates.append(Path(root) / "Adobe" / f"Adobe Photoshop {year}" / "Photoshop.exe")
    return candidates


def photoshop_status(photoshop_exe: str | Path | None = None) -> dict[str, Any]:
    exe = Path(photoshop_exe) if photoshop_exe else default_photoshop_exe()
    return {
        "available": exe.exists(),
        "photoshop_exe": str(exe),
        "mode": "jsx_desktop_bridge",
        "action_config": photoshop_action_status(),
    }


def create_photoshop_job(request: PhotoshopJobRequest) -> dict[str, Any]:
    source = Path(request.input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")

    batch_id = safe_batch_id(request.batch_id)
    job_id = _safe_job_id(request.photo_id) or uuid.uuid4().hex[:12]
    root = _photoshop_root(batch_id)
    jobs_dir = root / "jobs"
    output_dir = root / "output"
    psd_dir = root / "psd"
    scripts_dir = root / "scripts"
    for path in (jobs_dir, output_dir, psd_dir, scripts_dir):
        path.mkdir(parents=True, exist_ok=True)

    stem = _safe_file_stem(source.stem)
    output_path = Path(request.output_path) if request.output_path else output_dir / f"{stem}-ps-retouched.jpg"
    psd_path = Path(request.psd_path) if request.psd_path else psd_dir / f"{stem}-ps-retouched.psd"
    script_path = scripts_dir / f"{job_id}.jsx"
    marker_path = jobs_dir / f"{job_id}.result.json"
    job_path = jobs_dir / f"{job_id}.json"

    operations = apply_photoshop_action_config(request.operations)
    mask_assets = [dict(item) for item in request.mask_assets if isinstance(item, dict)]
    quality_mode = str(request.quality_mode or "standard").strip() or "standard"
    job = {
        "status": "queued",
        "job_id": job_id,
        "batch_id": batch_id,
        "photo_id": request.photo_id,
        "input_path": str(source),
        "output_path": str(output_path),
        "psd_path": str(psd_path),
        "script_path": str(script_path),
        "marker_path": str(marker_path),
        "job_path": str(job_path),
        "scene": request.scene,
        "aesthetic": request.aesthetic,
        "operations": operations,
        "mask_assets": mask_assets,
        "quality_mode": quality_mode,
        "strength": request.strength,
        "user_suggestion": clean_user_suggestion(request.user_suggestion),
        "message": f"Queued for Photoshop desktop execution ({quality_mode}).",
    }
    _write_job(job)
    script_path.write_text(build_photoshop_jsx(job), encoding="utf-8")
    append_event("photoshop_job_created", batch_id=batch_id, job_id=job_id, file=job_path.name)
    return job


def list_photoshop_jobs(batch_id: str) -> list[dict[str, Any]]:
    jobs_dir = _photoshop_root(safe_batch_id(batch_id)) / "jobs"
    if not jobs_dir.exists():
        return []
    jobs = [_read_json(path) for path in sorted(jobs_dir.glob("*.json")) if not path.name.endswith(".result.json")]
    return sorted((job for job in jobs if isinstance(job, dict)), key=lambda item: str(item.get("job_id", "")))


def get_next_photoshop_job(batch_id: str | None = None) -> dict[str, Any] | None:
    roots: list[Path]
    if batch_id:
        roots = [_photoshop_root(safe_batch_id(batch_id)) / "jobs"]
    else:
        root = run_root()
        roots = [path / "photoshop" / "jobs" for path in root.iterdir() if path.is_dir()] if root.exists() else []

    queued: list[dict[str, Any]] = []
    for jobs_dir in roots:
        if not jobs_dir.exists():
            continue
        for path in jobs_dir.glob("*.json"):
            if path.name.endswith(".result.json"):
                continue
            job = _read_json(path)
            if isinstance(job, dict) and job.get("status") == "queued":
                queued.append(job)
    if not queued:
        return None
    return sorted(queued, key=lambda item: str(item.get("job_id", "")))[0]


def mark_photoshop_job_complete(job_id: str, batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    job = _load_job(batch_id, job_id)
    payload = payload or {}
    output_path = payload.get("output_path") or job.get("output_path")
    psd_path = payload.get("psd_path") or job.get("psd_path")
    job.update(
        {
            "status": "completed",
            "output_path": str(output_path),
            "psd_path": str(psd_path),
            "message": str(payload.get("message") or "Photoshop job completed."),
            "result": payload,
        }
    )
    _write_job(job)
    append_event("photoshop_job_completed", batch_id=safe_batch_id(batch_id), job_id=job_id, file=Path(str(job["job_path"])).name)
    return job


def mark_photoshop_job_failed(job_id: str, batch_id: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    job = _load_job(batch_id, job_id)
    job.update(
        {
            "status": "failed",
            "message": message,
            "result": payload or {},
        }
    )
    _write_job(job)
    append_event("photoshop_job_failed", batch_id=safe_batch_id(batch_id), job_id=job_id, file=Path(str(job["job_path"])).name)
    return job


def run_photoshop_job(
    job_id: str,
    batch_id: str,
    photoshop_exe: str | Path | None = None,
    wait_seconds: int = 5,
) -> dict[str, Any]:
    job = _load_job(batch_id, job_id)
    exe = Path(photoshop_exe) if photoshop_exe else default_photoshop_exe()
    if not exe.exists():
        return mark_photoshop_job_failed(job_id, batch_id, f"Photoshop executable not found: {exe}")

    script_path = Path(str(job.get("script_path") or ""))
    script_path.write_text(build_photoshop_jsx(job), encoding="utf-8")
    marker_path = Path(str(job.get("marker_path") or ""))
    if marker_path.exists():
        try:
            marker_path.unlink()
        except OSError:
            pass

    job["status"] = "running"
    job["photoshop_exe"] = str(exe)
    job["message"] = "Photoshop process launched."
    _write_job(job)
    append_event("photoshop_job_started", batch_id=safe_batch_id(batch_id), job_id=job_id, file=script_path.name)

    subprocess.Popen([str(exe), "-r", str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + max(0, min(wait_seconds, DEFAULT_JOB_TIMEOUT_SECONDS))
    while wait_seconds > 0 and time.time() < deadline:
        if marker_path.exists():
            marker = _read_json(marker_path)
            if isinstance(marker, dict) and marker.get("status") == "ok":
                return mark_photoshop_job_complete(job_id, batch_id, marker)
            return mark_photoshop_job_failed(job_id, batch_id, str(marker.get("message") if isinstance(marker, dict) else "Photoshop job failed"), marker if isinstance(marker, dict) else {})
        time.sleep(0.5)

    return _load_job(batch_id, job_id)


def build_photoshop_jsx(job: dict[str, Any]) -> str:
    operations = job.get("operations") if isinstance(job.get("operations"), list) else []
    mask_assets = job.get("mask_assets") if isinstance(job.get("mask_assets"), list) else []
    op_names = [name for item in operations if isinstance(item, dict) for name in _operation_keys(item)]
    blemish_enabled = any(name in {"blemish_cleanup", "skin_cleanup"} for name in op_names)
    smoothing_enabled = any(name in {"skin_smoothing", "skin_texture_smoothing"} for name in op_names)
    commercial_skin_enabled = any(name in {"commercial_skin_retouch", "frequency_separation"} for name in op_names)
    face_liquify_enabled = any(name in {"face_slimming", "face_warp", "face_liquify"} for name in op_names)
    relight_enabled = any(name in {"face_relight", "portrait_relight", "landscape_dodge_burn"} for name in op_names)
    sky_enabled = any(name in {"sky_light_balance", "sky_balance"} for name in op_names)
    architecture_enabled = any(name in {"architecture_darken"} for name in op_names)
    foliage_boost_enabled = any(name in {"foliage_green_boost"} for name in op_names)
    foliage_enabled = any(name in {"foliage_tone_control", "foliage_control"} for name in op_names)

    input_path = _jsx_string(str(job["input_path"]))
    output_path = _jsx_string(str(job["output_path"]))
    psd_path = _jsx_string(str(job["psd_path"]))
    marker_path = _jsx_string(str(job["marker_path"]))
    note = _jsx_string(str(job.get("user_suggestion") or ""))
    operation_note = _jsx_string(_operation_note(operations))
    mask_note = _jsx_string(_mask_note(mask_assets))
    quality_mode = str(job.get("quality_mode") or "standard")
    operation_count = len(operations)
    mask_count = len(mask_assets)
    blemish_block = _blemish_layer_jsx(_action_for(operations, "blemish_cleanup", "skin_cleanup")) if blemish_enabled else ""
    smooth_block = _smooth_layer_jsx(_action_for(operations, "skin_smoothing", "skin_texture_smoothing")) if smoothing_enabled else ""
    commercial_skin_block = _frequency_separation_layer_jsx(_action_for(operations, "frequency_separation", "commercial_skin_retouch")) if commercial_skin_enabled else ""
    face_liquify_block = _face_liquify_layer_jsx(_action_for(operations, "face_liquify", "face_slimming", "face_warp")) if face_liquify_enabled else ""
    relight_block = _relight_layer_jsx(_action_for(operations, "face_relight", "portrait_relight", "landscape_dodge_burn")) if relight_enabled else ""
    sky_block = _sky_layer_jsx(_action_for(operations, "sky_light_balance", "sky_balance")) if sky_enabled else ""
    architecture_block = _architecture_layer_jsx(_action_for(operations, "architecture_darken")) if architecture_enabled else ""
    foliage_boost_block = _foliage_boost_layer_jsx(_action_for(operations, "foliage_green_boost")) if foliage_boost_enabled else ""
    foliage_block = _foliage_layer_jsx(_action_for(operations, "foliage_tone_control", "foliage_control")) if foliage_enabled else ""
    mask_guide_block = _mask_guide_jsx(mask_assets)
    return f"""#target photoshop
app.displayDialogs = DialogModes.NO;
var actionLog = [];

function jsonEscape(value) {{
    return String(value).replace(/\\\\/g, "\\\\\\\\").replace(/"/g, "\\\\\\"").replace(/\\r/g, "\\\\r").replace(/\\n/g, "\\\\n");
}}

function runActionHook(operation, actionSet, actionName, required) {{
    if (!actionSet || !actionName) {{
        actionLog.push(operation + ": no action configured");
        return;
    }}
    try {{
        app.doAction(actionName, actionSet);
        actionLog.push(operation + ": action ok " + actionSet + "/" + actionName);
    }} catch (actionErr) {{
        actionLog.push(operation + ": action failed " + String(actionErr));
        if (required) {{
            throw actionErr;
        }}
    }}
}}

function addMaskGuide(maskPath, maskName) {{
    try {{
        var maskFile = new File(maskPath);
        if (!maskFile.exists) {{
            actionLog.push("mask missing " + maskName);
            return;
        }}
        var targetDoc = app.activeDocument;
        var maskDoc = app.open(maskFile);
        maskDoc.activeLayer.name = "AI mask guide - " + maskName;
        maskDoc.activeLayer.duplicate(targetDoc, ElementPlacement.PLACEATBEGINNING);
        maskDoc.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = targetDoc;
        targetDoc.activeLayer.name = "AI mask guide - " + maskName;
        targetDoc.activeLayer.visible = false;
        actionLog.push("mask guide added " + maskName);
    }} catch (maskErr) {{
        actionLog.push("mask guide failed " + maskName + ": " + String(maskErr));
    }}
}}

function writeResult(status, message) {{
    var file = new File({marker_path});
    file.encoding = "UTF8";
    file.open("w");
    file.write('{{"status":"' + jsonEscape(status) + '","message":"' + jsonEscape(message) + '","output_path":"' + jsonEscape({output_path}) + '","psd_path":"' + jsonEscape({psd_path}) + '","quality_mode":{json.dumps(quality_mode)},"operation_count":{operation_count},"mask_count":{mask_count},"action_log":"' + jsonEscape(actionLog.join(" | ")) + '"}}');
    file.close();
}}

try {{
    var inputFile = new File({input_path});
    if (!inputFile.exists) {{
        throw new Error("Input file does not exist");
    }}
    var doc = app.open(inputFile);
    var sourceLayer = doc.activeLayer;
    sourceLayer.name = "AI source";
    var noteLayer = doc.artLayers.add();
    noteLayer.name = "AI retouch plan - " + {note};
    noteLayer.visible = false;
    var opsLayer = doc.artLayers.add();
    opsLayer.name = "AI operations - " + {operation_note};
    opsLayer.visible = false;
    var maskLayer = doc.artLayers.add();
    maskLayer.name = "AI mask guide - " + {mask_note};
    maskLayer.visible = false;
    doc.activeLayer = sourceLayer;
{mask_guide_block}
{blemish_block}
{smooth_block}
{commercial_skin_block}
{face_liquify_block}
{relight_block}
{sky_block}
{architecture_block}
{foliage_boost_block}
{foliage_block}
    var psdFile = new File({psd_path});
    psdFile.parent.create();
    var psdOptions = new PhotoshopSaveOptions();
    psdOptions.layers = true;
    doc.saveAs(psdFile, psdOptions, true, Extension.LOWERCASE);

    var outputFile = new File({output_path});
    outputFile.parent.create();
    var jpgOptions = new JPEGSaveOptions();
    jpgOptions.quality = 12;
    doc.saveAs(outputFile, jpgOptions, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    writeResult("ok", "Photoshop job completed");
}} catch (err) {{
    writeResult("failed", String(err));
}}
"""


def _operation_note(operations: list[Any]) -> str:
    names: list[str] = []
    for item in operations:
        if isinstance(item, dict):
            keys = _operation_keys(item)
            name = keys[0] if keys else ""
            region = str(item.get("region_id") or item.get("target") or "").strip()
            mask = str(item.get("mask_path") or "").strip()
            mask_name = Path(mask).name if mask else ""
            if name:
                suffix = f":{region}" if region else ""
                if mask_name:
                    suffix += f" mask={mask_name}"
                names.append(f"{name}{suffix}")
    return ", ".join(names)[:180] if names else "none"


def _operation_keys(operation: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in (operation.get("type"), operation.get("id")):
        value = str(key or "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


def _mask_note(mask_assets: list[Any]) -> str:
    names: list[str] = []
    for item in mask_assets:
        if not isinstance(item, dict):
            continue
        mask_id = str(item.get("id") or "").strip()
        path = str(item.get("path") or "").strip()
        if mask_id:
            names.append(f"{mask_id}={Path(path).name if path else 'no-file'}")
    return ", ".join(names)[:220] if names else "none"


def _mask_guide_jsx(mask_assets: list[Any]) -> str:
    lines: list[str] = []
    for item in mask_assets[:12]:
        if not isinstance(item, dict):
            continue
        mask_id = str(item.get("id") or "").strip()
        mask_path = str(item.get("path") or "").strip()
        if not mask_id or not mask_path:
            continue
        lines.append(f"    addMaskGuide({_jsx_string(mask_path)}, {_jsx_string(mask_id)});\n")
    return "".join(lines)


def _action_for(operations: list[Any], *names: str) -> dict[str, Any]:
    name_set = set(names)
    for item in operations:
        if not isinstance(item, dict):
            continue
        if not any(operation_name in name_set for operation_name in _operation_keys(item)):
            continue
        action = item.get("photoshop_action")
        return action if isinstance(action, dict) else {}
    return {}


def _action_hook_jsx(operation: str, action: dict[str, Any]) -> str:
    action_set = _jsx_string(str(action.get("set") or ""))
    action_name = _jsx_string(str(action.get("action") or ""))
    required = "true" if action.get("required") is True else "false"
    return f'    runActionHook("{operation}", {action_set}, {action_name}, {required});\n'


def _blemish_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var blemishLayer = sourceLayer.duplicate();
    blemishLayer.name = "AI blemish cleanup candidate - manual review";
    blemishLayer.opacity = 100;
    doc.activeLayer = blemishLayer;
""" + _action_hook_jsx("blemish_cleanup", action)


def _smooth_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var smoothLayer = sourceLayer.duplicate();
    smoothLayer.name = "AI skin smoothing candidate";
    smoothLayer.opacity = 28;
    doc.activeLayer = smoothLayer;
    try {
        smoothLayer.applyGaussianBlur(1.2);
    } catch (adjustErr) {
        actionLog.push("skin_smoothing: gaussian blur fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("skin_smoothing", action)


def _frequency_separation_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var lowFreqLayer = sourceLayer.duplicate();
    lowFreqLayer.name = "AI frequency separation low-frequency candidate";
    lowFreqLayer.opacity = 38;
    doc.activeLayer = lowFreqLayer;
    try {
        lowFreqLayer.applyGaussianBlur(2.2);
    } catch (adjustErr) {
        actionLog.push("frequency_separation: gaussian blur fallback failed " + String(adjustErr));
    }
    doc.activeLayer = sourceLayer;
    var textureGuideLayer = sourceLayer.duplicate();
    textureGuideLayer.name = "AI texture preservation guide - commercial retouch";
    textureGuideLayer.opacity = 100;
    doc.activeLayer = textureGuideLayer;
""" + _action_hook_jsx("frequency_separation", action)


def _face_liquify_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var faceShapeLayer = sourceLayer.duplicate();
    faceShapeLayer.name = "AI face liquify candidate - requires Liquify/action";
    faceShapeLayer.opacity = 100;
    doc.activeLayer = faceShapeLayer;
""" + _action_hook_jsx("face_liquify", action)


def _relight_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var relightLayer = sourceLayer.duplicate();
    relightLayer.name = "AI local light candidate";
    relightLayer.opacity = 18;
    doc.activeLayer = relightLayer;
    try {
        relightLayer.adjustBrightnessContrast(8, 4);
    } catch (adjustErr) {
        actionLog.push("local_relight: brightness fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("local_relight", action)


def _sky_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var skyLayer = sourceLayer.duplicate();
    skyLayer.name = "AI sky balance candidate";
    skyLayer.opacity = 22;
    doc.activeLayer = skyLayer;
    try {
        skyLayer.adjustBrightnessContrast(-4, 8);
    } catch (adjustErr) {
        actionLog.push("sky_light_balance: brightness fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("sky_light_balance", action)


def _architecture_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var architectureLayer = sourceLayer.duplicate();
    architectureLayer.name = "AI architecture exposure candidate";
    architectureLayer.opacity = 26;
    doc.activeLayer = architectureLayer;
    try {
        architectureLayer.adjustBrightnessContrast(-10, 6);
    } catch (adjustErr) {
        actionLog.push("architecture_darken: brightness fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("architecture_darken", action)


def _foliage_boost_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var foliageBoostLayer = sourceLayer.duplicate();
    foliageBoostLayer.name = "AI foliage green boost candidate";
    foliageBoostLayer.opacity = 24;
    doc.activeLayer = foliageBoostLayer;
    try {
        foliageBoostLayer.adjustBrightnessContrast(2, 5);
    } catch (adjustErr) {
        actionLog.push("foliage_green_boost: fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("foliage_green_boost", action)


def _foliage_layer_jsx(action: dict[str, Any]) -> str:
    return """    doc.activeLayer = sourceLayer;
    var foliageLayer = sourceLayer.duplicate();
    foliageLayer.name = "AI foliage tone candidate";
    foliageLayer.opacity = 18;
    doc.activeLayer = foliageLayer;
    try {
        foliageLayer.adjustBrightnessContrast(-2, 6);
    } catch (adjustErr) {
        actionLog.push("foliage_tone_control: fallback failed " + String(adjustErr));
    }
""" + _action_hook_jsx("foliage_tone_control", action)


def _photoshop_root(batch_id: str) -> Path:
    return batch_dir(batch_id) / "photoshop"


def _load_job(batch_id: str, job_id: str) -> dict[str, Any]:
    path = _photoshop_root(safe_batch_id(batch_id)) / "jobs" / f"{_safe_job_id(job_id)}.json"
    if not path.exists():
        raise FileNotFoundError(f"Photoshop job not found: {job_id}")
    job = _read_json(path)
    if not isinstance(job, dict):
        raise ValueError(f"Invalid Photoshop job file: {path}")
    return job


def _write_job(job: dict[str, Any]) -> None:
    path = Path(str(job["job_path"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_job_id(value: Any) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value or ""))
    return clean.strip("_")[-80:]


def _safe_file_stem(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return clean.strip("_") or "photo"


def _jsx_string(value: str) -> str:
    return json.dumps(value.replace("\\", "/"), ensure_ascii=False)
