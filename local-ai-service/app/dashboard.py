from __future__ import annotations

import json
import tempfile
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import __version__
from .ai_connection import test_ai_config
from .config import AIConfig, codex_reference_config, load_ai_config, public_ai_config, save_ai_config
from .lightroom_params import supported_aesthetics, supported_edit_levels, supported_scenes, supported_styles
from .photoshop_bridge import photoshop_status
from .storage import batch_files, list_batches, read_batch_json, recent_events, run_root

router = APIRouter()

PARAM_LABELS = {
    "exposure": "曝光",
    "contrast": "对比度",
    "highlights": "高光",
    "shadows": "阴影",
    "whites": "白色色阶",
    "blacks": "黑色色阶",
    "temperature": "白平衡色温",
    "tint": "色调",
    "texture": "纹理",
    "clarity": "清晰度",
    "dehaze": "去朦胧",
    "vibrance": "自然饱和度",
    "saturation": "饱和度",
    "sharpening": "锐化",
    "noise_reduction": "降噪",
}

COLOR_LABELS = {
    "Red": "红色",
    "Orange": "橙色",
    "Yellow": "黄色",
    "Green": "绿色",
    "Aqua": "青色",
    "Blue": "蓝色",
    "Purple": "紫色",
    "Magenta": "洋红",
}

ADVANCED_SETTING_LABELS = {
    "ParametricShadows": "曲线阴影",
    "ParametricDarks": "曲线暗调",
    "ParametricLights": "曲线亮调",
    "ParametricHighlights": "曲线高光",
    "ParametricShadowSplit": "曲线阴影分离点",
    "ParametricMidtoneSplit": "曲线中间调分离点",
    "ParametricHighlightSplit": "曲线高光分离点",
    "SplitToningHighlightHue": "高光色相",
    "SplitToningHighlightSaturation": "高光饱和度",
    "SplitToningShadowHue": "阴影色相",
    "SplitToningShadowSaturation": "阴影饱和度",
    "SplitToningBalance": "色彩分级平衡",
    "CropLeft": "裁剪左边界",
    "CropTop": "裁剪上边界",
    "CropRight": "裁剪右边界",
    "CropBottom": "裁剪下边界",
    "CropAngle": "裁剪角度",
    "PostCropVignetteAmount": "暗角数量",
    "PostCropVignetteMidpoint": "暗角中点",
    "PostCropVignetteFeather": "暗角羽化",
    "PostCropVignetteRoundness": "暗角圆度",
    "PostCropVignetteStyle": "暗角样式",
}

OPERATION_LABELS = {
    "skin_cleanup": "去瑕疵",
    "blemish_cleanup": "去瑕疵",
    "skin_texture_smoothing": "磨皮/肤质平滑",
    "skin_smoothing": "磨皮/肤质平滑",
    "commercial_skin_retouch": "商业级磨皮/频率分离",
    "frequency_separation": "商业级磨皮/频率分离",
    "face_relight": "人脸补光",
    "face_slimming": "瘦脸",
    "face_warp": "瘦脸",
    "face_liquify": "液化/瘦脸",
    "sky_light_balance": "天空光影",
    "sky_balance": "天空光影",
    "landscape_dodge_burn": "风景光影",
    "architecture_darken": "建筑/前景压暗",
    "foliage_green_boost": "草地/绿植增强",
    "foliage_tone_control": "绿植色彩控制",
}

METRIC_LABELS = {
    "avg_luma": "平均亮度",
    "highlight_clip": "高光溢出",
    "shadow_clip": "暗部死黑",
    "avg_saturation": "平均饱和度",
    "warmth": "冷暖偏移",
    "sharpness": "锐度",
}

STYLE_LABELS = {
    "natural_portrait": "自然人像",
    "wedding_clean": "婚纱干净风",
    "kids_soft": "儿童柔和风",
    "indoor_portrait": "室内写真",
    "outdoor_backlight": "户外逆光",
}

SCENE_LABELS = {
    "auto": "自动识别",
    "portrait": "人像",
    "wedding": "婚纱",
    "children": "儿童",
    "indoor_portrait": "室内写真",
    "outdoor_backlight": "户外逆光",
    "landscape": "风景",
    "flower": "花卉",
    "grass_tree": "草地树木",
    "forest": "森林",
    "architecture": "城市建筑",
    "sunset": "日落晚霞",
    "blue_sky": "蓝天白云",
    "night": "夜景",
    "food": "美食",
    "still_life": "静物",
}

AESTHETIC_LABELS = {
    "auto": "自动",
    "natural": "自然",
    "sweet": "糖水片",
    "texture": "质感片",
    "master": "大师风",
    "japanese_clear": "日系清透",
    "film": "胶片感",
    "commercial_clean": "商业干净",
    "documentary": "纪实自然",
    "warm_soft": "暖调柔和",
    "cool_transparent": "冷调通透",
    "high_gray": "高级灰",
}

EDIT_LEVEL_LABELS = {
    "basic": "基础修图",
    "basic_plus_advanced_suggestions": "基础修图 + 进阶建议",
    "basic_plus_advanced_execute": "基础修图 + 进阶执行",
}

SKIN_TARGET_LABELS = {
    "warm_neutral": "暖中性肤色",
    "warm_clean": "干净暖肤色",
    "neutral_texture": "中性质感肤色",
    "not_primary": "非人像优先",
}

CONTRAST_LABELS = {
    "soft": "柔和",
    "natural": "自然",
    "strong": "强质感",
}

ISSUE_LABELS = {
    "too_dark": "画面偏暗",
    "too_bright": "画面偏亮",
    "highlights_clipped": "高光溢出",
    "shadows_blocked": "暗部死黑",
    "over_saturated": "饱和度过高",
    "too_warm": "色温偏暖",
    "too_cool": "色温偏冷",
    "needs_minor_tuning": "需要轻微微调",
}

EVENT_LABELS = {
    "save_json": "保存批次数据",
}

SOURCE_LABELS = {
    "Custom API": "自定义接口",
    "Relay API": "中转站 API",
    "OpenAI-compatible API": "OpenAI 兼容接口",
    "Rules": "本地规则",
    "rules": "本地规则",
    "自定义接口": "自定义接口",
    "中转站 API": "中转站 API",
    "OpenAI 兼容接口": "OpenAI 兼容接口",
    "本地规则": "本地规则",
}


def _page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17202a;
      background: #f5f7fb;
    }}
    body {{ margin: 0; }}
    header {{
      background: #152238;
      color: #fff;
      padding: 18px 28px;
    }}
    header h1 {{ margin: 0; font-size: 20px; font-weight: 650; }}
    nav {{ margin-top: 8px; display: flex; gap: 14px; flex-wrap: wrap; }}
    nav a {{ color: #dbeafe; text-decoration: none; font-size: 14px; }}
    main {{ padding: 24px 28px; max-width: 1280px; margin: 0 auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
    .panel {{
      background: #fff;
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}
    .label {{ color: #607087; font-size: 13px; margin-bottom: 6px; }}
    .value {{ font-size: 20px; font-weight: 650; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9e2ef; }}
    th, td {{ border-bottom: 1px solid #e6edf6; padding: 10px 12px; text-align: left; font-size: 14px; vertical-align: top; }}
    th {{ background: #edf3fb; color: #43536a; }}
    code, pre {{ font-family: Consolas, "Courier New", monospace; }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #0f172a;
      color: #e5e7eb;
      border-radius: 8px;
      padding: 14px;
      line-height: 1.45;
      font-size: 13px;
    }}
    .muted {{ color: #607087; }}
    .section-title {{ margin: 24px 0 10px; font-size: 17px; }}
    .small {{ font-size: 12px; }}
    .pill {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      line-height: 18px;
      background: #e8f1ff;
      color: #174f92;
      margin: 1px 4px 3px 0;
    }}
    .pill.warn {{ background: #fff2d6; color: #8a5700; }}
    .pill.good {{ background: #def7ec; color: #176b48; }}
    .changes {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .change {{
      display: inline-flex;
      gap: 5px;
      align-items: center;
      background: #f4f7fb;
      border: 1px solid #dbe4f0;
      border-radius: 6px;
      padding: 4px 7px;
      font-size: 12px;
      white-space: nowrap;
    }}
    .change strong {{ color: #26384f; }}
    .positive {{ color: #0f766e; }}
    .negative {{ color: #b42318; }}
    .reason-list {{ margin: 0; padding-left: 18px; }}
    .compare-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
    .compare-card {{ background: #fff; border: 1px solid #d9e2ef; border-radius: 8px; padding: 12px; }}
    .compare-images {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin-top: 8px; }}
    .preview-frame {{ background: #111827; border-radius: 6px; overflow: hidden; min-height: 150px; display: flex; align-items: center; justify-content: center; }}
    .preview-frame img {{ width: 100%; height: 220px; object-fit: contain; display: block; }}
    .preview-frame a {{ display: block; width: 100%; position: relative; text-decoration: none; }}
    .preview-frame a::after {{
      content: "点击放大";
      position: absolute;
      right: 8px;
      bottom: 8px;
      background: rgba(15, 23, 42, 0.78);
      color: #fff;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
    }}
    .preview-caption {{ font-size: 12px; color: #607087; margin-bottom: 4px; }}
    input, select, button {{
      border: 1px solid #c9d6e6;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 14px;
      background: #fff;
    }}
    input, select {{ width: 100%; box-sizing: border-box; }}
    button {{ cursor: pointer; background: #1456a0; color: #fff; border-color: #1456a0; }}
    a {{ color: #1456a0; }}
  </style>
</head>
<body>
  <header>
    <h1>智能修图控制台</h1>
    <nav>
      <a href="/dashboard">系统状态</a>
      <a href="/dashboard/runs">批次记录</a>
      <a href="/dashboard/config">AI 配置</a>
      <a href="/docs">接口文档</a>
      <a href="/health">健康检查</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>"""
    return HTMLResponse(html)


@router.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return dashboard()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    batches = list_batches()
    events = recent_events(12)
    scenes = [SCENE_LABELS.get(scene, scene) for scene in supported_scenes()]
    aesthetics = [AESTHETIC_LABELS.get(item, item) for item in supported_aesthetics()]
    edit_levels = [EDIT_LEVEL_LABELS.get(item, item) for item in supported_edit_levels()]
    ai_config = public_ai_config()
    ai_status = "已配置" if ai_config["configured"] else "规则模式"
    ps_status = photoshop_status()
    ps_available = "可用" if ps_status.get("available") else "未找到"
    body = f"""
<div class="grid">
  <div class="panel"><div class="label">服务状态</div><div class="value">运行中</div></div>
  <div class="panel"><div class="label">版本</div><div class="value">{escape(__version__)}</div></div>
  <div class="panel"><div class="label">批次数</div><div class="value">{len(batches)}</div></div>
  <div class="panel"><div class="label">AI 接口</div><div class="value">{escape(ai_status)}</div><div class="small muted">{escape(str(ai_config["provider"]))}</div></div>
  <div class="panel"><div class="label">Photoshop 桥接</div><div class="value">{escape(ps_available)}</div><div class="small muted">{escape(str(ps_status.get("photoshop_exe") or ""))}</div></div>
</div>
<h2 class="section-title">支持场景</h2>
<div class="panel">{escape("、".join(scenes))}</div>
<h2 class="section-title">支持审美</h2>
<div class="panel">{escape("、".join(aesthetics))}</div>
<h2 class="section-title">当前流程能力</h2>
<div class="panel">
  <div>Lightroom 基础参数、Lightroom 可执行进阶参数、用户建议优先级、局部蒙版分析、本地像素精修、Photoshop 商业级动作桥接、PSD/JPG 输出、人工确认后最终导出。</div>
  <div class="small muted" style="margin-top:6px">处理层级：{escape("、".join(edit_levels))}</div>
</div>
<h2 class="section-title">数据目录</h2>
<div class="panel">{escape(str(run_root()))}</div>
<h2 class="section-title">最近批次</h2>
{_runs_table(batches[:8])}
<h2 class="section-title">最近事件</h2>
{_events_table(events)}
"""
    return _page("智能修图控制台", body)


@router.get("/dashboard/runs", response_class=HTMLResponse)
def runs_page() -> HTMLResponse:
    return _page("批次记录", f'<h2 class="section-title">全部批次</h2>{_runs_table(list_batches())}')


@router.get("/dashboard/image")
def dashboard_image(path: str) -> FileResponse:
    image_path = _safe_image_path(path)
    return FileResponse(
        image_path,
        media_type=_image_media_type(image_path),
        headers={"Content-Disposition": "inline"},
    )


@router.get("/dashboard/image-view", response_class=HTMLResponse)
def dashboard_image_view(path: str, return_to: str = "/dashboard/runs") -> HTMLResponse:
    image_path = _safe_image_path(path)
    url = _image_url(str(image_path))
    return_url = _safe_dashboard_return_url(return_to)
    body = f"""
<p><a href="{escape(return_url, quote=True)}">返回</a></p>
<div class="panel">
  <img src="{escape(url)}" alt="放大预览" style="display:block; width:100%; max-height:82vh; object-fit:contain; background:#111827; border-radius:6px">
</div>
"""
    return _page("放大预览", body)


@router.get("/dashboard/config", response_class=HTMLResponse)
def config_page() -> HTMLResponse:
    return _config_page()


def _config_page(test_result: dict[str, Any] | None = None) -> HTMLResponse:
    config = load_ai_config()
    codex = codex_reference_config()
    checked = "checked" if config.enabled else ""
    base_url_value = config.public_base_url
    warnings = "".join(f'<div class="small muted">{escape(item)}</div>' for item in config.warnings)
    body = f"""
<h2 class="section-title">AI 配置</h2>
<div class="panel">
  <form method="post" action="/dashboard/config">
    <div class="grid">
      <label>
        <div class="label">启用外部 AI</div>
        <input type="checkbox" name="enabled" value="true" {checked}> 启用
      </label>
      <label>
        <div class="label">提供商</div>
        <select name="provider">
          {_option("mock", "规则模式（不调用外部 AI）", config.provider)}
          {_option("openai_relay", "中转站 API（OpenAI 兼容）", config.provider)}
          {_option("openai_compatible", "OpenAI 兼容接口", config.provider)}
          {_option("custom", "自定义接口", config.provider)}
        </select>
      </label>
      <label>
        <div class="label">接口类型</div>
        <select name="wire_api">
          {_option("openai_relay", "OpenAI 中转站（自动检测）", config.wire_api)}
          {_option("responses", "Responses API（Codex 配置常用）", config.wire_api)}
          {_option("chat_completions", "Chat Completions API", config.wire_api)}
          {_option("completions", "Completions API（/completions）", config.wire_api)}
          {_option("legacy_completions", "Engine Completions API（/engines/{model}/completions）", config.wire_api)}
        </select>
      </label>
      <label>
        <div class="label">模型名称</div>
        <input name="model" value="{escape(config.model)}" placeholder="例如：你的视觉模型名称">
      </label>
      <label>
        <div class="label">接口地址</div>
        <input name="base_url" value="{escape(base_url_value)}" placeholder="例如：https://api.example.com/v1">
      </label>
    </div>
    <div style="margin-top:14px">
      <label>
        <div class="label">API Key</div>
        <input name="api_key" type="password" value="" placeholder="留空表示保留现有密钥：{escape(config.masked_api_key or '未配置')}" style="width:100%; box-sizing:border-box">
      </label>
    </div>
    <div class="small muted" style="margin-top:10px">
      当前状态：{escape('已配置' if config.configured else '未启用或未配置密钥')}。密钥保存在本机 local-ai-service/config/settings.json，不会在页面回显完整内容。
      {warnings}
    </div>
    <div style="margin-top:16px">
      <button type="submit">保存配置</button>
    </div>
  </form>
  <form method="post" action="/dashboard/config/test" style="margin-top:12px">
    <button type="submit">测试 AI 配置</button>
  </form>
  {_config_test_result_html(test_result)}
</div>
{_codex_reference_html(codex)}
"""
    return _page("AI 配置", body)


@router.post("/dashboard/config")
def save_config_page(
    provider: str = Form("mock"),
    base_url: str = Form(""),
    model: str = Form(""),
    wire_api: str = Form("responses"),
    api_key: str = Form(""),
    enabled: str | None = Form(None),
) -> RedirectResponse:
    existing = load_ai_config()
    config = AIConfig(
        provider=provider.strip() or "mock",
        base_url=base_url.strip(),
        model=model.strip(),
        wire_api=wire_api.strip() or "responses",
        api_key=api_key.strip() or existing.api_key,
        enabled=enabled == "true",
    )
    save_ai_config(config)
    return RedirectResponse("/dashboard/config", status_code=303)


@router.post("/dashboard/config/test", response_class=HTMLResponse)
def test_config_page() -> HTMLResponse:
    return _config_page(test_ai_config())


@router.get("/dashboard/runs/{batch_id}", response_class=HTMLResponse)
def run_detail_page(batch_id: str) -> HTMLResponse:
    try:
        files = batch_files(batch_id)
        summary = _load_edit_summary(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    body = f"""
<h2 class="section-title">批次 {escape(batch_id)}</h2>
{_summary_cards(summary)}
<h2 class="section-title">修图概览</h2>
{_group_summary(summary)}
<h2 class="section-title">修图前后对比</h2>
{_preview_compare_grid(summary, _dashboard_run_url(batch_id))}
<h2 class="section-title">单张修改明细</h2>
{_photo_changes_table(summary)}
<h2 class="section-title">审核与二次修正</h2>
{_review_table(summary)}
<h2 class="section-title">原始数据文件</h2>
{_files_table(batch_id, files)}
"""
    return _page(f"批次 {batch_id}", body)


@router.get("/dashboard/runs/{batch_id}/edit-summary", response_class=HTMLResponse)
def run_edit_summary_page(batch_id: str) -> HTMLResponse:
    try:
        summary = _load_edit_summary(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    batch_url = _dashboard_run_url(batch_id)
    body = f"""
<p><a href="{batch_url}">返回批次</a></p>
<h2 class="section-title">修图说明 / {escape(batch_id)}</h2>
{_summary_cards(summary)}
<h2 class="section-title">修图概览</h2>
{_group_summary(summary)}
<h2 class="section-title">修图前后对比</h2>
{_preview_compare_grid(summary, _dashboard_run_url(batch_id, "edit-summary"))}
<h2 class="section-title">单张修改明细</h2>
{_photo_changes_table(summary)}
<h2 class="section-title">审核与二次修正</h2>
{_review_table(summary)}
"""
    return _page(f"修图说明 {batch_id}", body)


@router.get("/dashboard/runs/{batch_id}/{file_name}", response_class=HTMLResponse)
def run_file_page(batch_id: str, file_name: str) -> HTMLResponse:
    try:
        payload = read_batch_json(batch_id, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=file_name) from exc

    pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    batch_url = _dashboard_run_url(batch_id)
    body = f"""
<p><a href="{batch_url}">返回批次</a></p>
<h2 class="section-title">{escape(batch_id)} / {escape(file_name)}</h2>
<pre>{escape(pretty)}</pre>
"""
    return _page(file_name, body)


@router.get("/api/status")
def api_status() -> dict[str, Any]:
    batches = list_batches()
    ai_config = public_ai_config()
    return {
        "status": "ok",
        "version": __version__,
        "run_root": str(run_root()),
        "batch_count": len(batches),
        "supported_styles": supported_styles(),
        "supported_scenes": supported_scenes(),
        "supported_aesthetics": supported_aesthetics(),
        "supported_edit_levels": supported_edit_levels(),
        "ai_config": ai_config,
    }


@router.get("/api/config")
def api_config() -> dict[str, Any]:
    return public_ai_config()


@router.post("/api/config/test")
def api_config_test() -> dict[str, Any]:
    return test_ai_config()


@router.get("/api/runs")
def api_runs() -> list[dict[str, Any]]:
    return list_batches()


@router.get("/api/runs/{batch_id}")
def api_run(batch_id: str) -> dict[str, Any]:
    try:
        return {"batch_id": batch_id, "files": batch_files(batch_id), "edit_summary": _load_edit_summary(batch_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/runs/{batch_id}/edit-summary")
def api_edit_summary(batch_id: str) -> dict[str, Any]:
    try:
        return _load_edit_summary(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/runs/{batch_id}/{file_name}")
def api_run_file(batch_id: str, file_name: str) -> dict[str, Any]:
    try:
        return read_batch_json(batch_id, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=file_name) from exc


@router.get("/api/events")
def api_events(limit: int = 100) -> list[dict[str, Any]]:
    return recent_events(max(1, min(limit, 500)))


def _load_edit_summary(batch_id: str) -> dict[str, Any]:
    analyze = _optional_payload(batch_id, "analyze.json")
    apply_plan = _optional_payload(batch_id, "apply-plan.json")
    export_report = _optional_payload(batch_id, "export-report.json")
    reviews = _load_reviews(batch_id)
    pixel_reports = _load_payloads_with_prefix(batch_id, "pixel-retouch-")
    photoshop_reports = _load_payloads_with_prefix(batch_id, "photoshop-retouch-")

    analyze_photos = analyze.get("photos", []) if analyze else []
    apply_photos = apply_plan.get("photos", []) if apply_plan else []
    latest_params_by_id = {item.get("photo_id"): item.get("params", {}) for item in apply_photos}
    review_by_id = _latest_review_by_id(reviews)
    pixel_report_by_id = _reports_by_photo_id(pixel_reports)
    photoshop_report_by_id = _reports_by_photo_id(photoshop_reports)

    photos = []
    for item in analyze_photos:
        photo_id = item.get("photo_id", "")
        initial_params = item.get("params", {})
        final_params = latest_params_by_id.get(photo_id, initial_params)
        review = review_by_id.get(photo_id, {})
        before_path = _nested_get(review, ["metrics", "before", "path"]) or item.get("metrics", {}).get("path")
        basic_after_path = _nested_get(review, ["metrics", "after", "path"])
        retouch_path = _retouch_preview_path(
            pixel_report_by_id.get(photo_id),
            photoshop_report_by_id.get(photo_id),
        )
        changed_params = _changed_params(final_params)
        advanced_plan = item.get("advanced_plan", {})
        advanced_changes = _advanced_changes_from_plan(advanced_plan)
        local_analysis = item.get("local_analysis", {}) if isinstance(item.get("local_analysis"), dict) else {}
        photos.append(
            {
                "photo_id": photo_id,
                "file_name": item.get("file_name", photo_id),
                "detected_scene": item.get("detected_scene", ""),
                "ai_source": item.get("ai_source", "rules"),
                "ai_notes": item.get("ai_notes", []),
                "initial_params": initial_params,
                "final_params": final_params,
                "changed_params": changed_params,
                "advanced_changes": advanced_changes,
                "modification_count": len(changed_params) + len(advanced_changes),
                "review": review,
                "metrics": item.get("metrics", {}),
                "local_analysis": local_analysis,
                "photo_user_suggestion": local_analysis.get("user_suggestion", ""),
                "before_preview_url": _image_url(before_path),
                "basic_preview_url": _image_url(basic_after_path),
                "retouch_preview_url": _image_url(retouch_path),
                "after_preview_url": _image_url(retouch_path or basic_after_path),
                "reasons": _reasons_from_metrics(item.get("metrics", {}), initial_params),
                "advanced_suggestions": item.get("advanced_suggestions", []),
                "crop_suggestion": item.get("crop_suggestion", {}),
                "advanced_plan": advanced_plan,
            }
        )

    scene_counts = _scene_counts(photos, analyze.get("scene") if analyze else None)
    return {
        "batch_id": batch_id,
        "style": analyze.get("style") if analyze else None,
        "scene": analyze.get("scene") if analyze else None,
        "aesthetic": analyze.get("aesthetic") if analyze else None,
        "edit_level": analyze.get("edit_level") if analyze else None,
        "user_suggestion": analyze.get("user_suggestion", "") if analyze else "",
        "ai_status": analyze.get("ai_status", {}) if analyze else {},
        "group_style": analyze.get("group_style", {}) if analyze else {},
        "photo_count": len(photos),
        "review_count": len(reviews),
        "latest_review": reviews[-1] if reviews else {},
        "export_report": export_report,
        "pixel_reports": pixel_reports,
        "photoshop_reports": photoshop_reports,
        "scene_counts": scene_counts,
        "advanced_status": _advanced_batch_status(photos),
        "retouch_status": _retouch_batch_status(pixel_reports, photoshop_reports, export_report, photos),
        "photos": photos,
    }


def _reports_by_photo_id(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for report in reports:
        photo_id = str(report.get("photo_id") or _nested_get(report, ["job", "photo_id"]) or "").strip()
        if photo_id:
            result[photo_id] = report
    return result


def _retouch_preview_path(pixel_report: dict[str, Any] | None, photoshop_report: dict[str, Any] | None) -> str:
    for report in (photoshop_report, pixel_report):
        if not report:
            continue
        status = str(report.get("status") or _nested_get(report, ["job", "status"]) or "").lower()
        if status and status not in {"completed", "ok", "done"}:
            continue
        output_path = report.get("output_path") or _nested_get(report, ["job", "output_path"])
        if _preview_file_exists(output_path):
            return str(output_path)
    return ""


def _preview_file_exists(path: Any) -> bool:
    if not path:
        return False
    try:
        resolved = Path(str(path)).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return resolved.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}


def _nested_get(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _image_url(path: Any) -> str:
    if not path:
        return ""
    return "/dashboard/image?path=" + quote(str(path), safe="")


def _safe_image_path(path: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    if resolved.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=404, detail="Unsupported image type")
    allowed = _allowed_image_roots()
    if not any(resolved == root or root in resolved.parents for root in allowed):
        raise HTTPException(status_code=403, detail="Image path is not allowed")
    return resolved


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _allowed_image_roots() -> list[Path]:
    roots = [run_root().resolve()]
    temp_root = Path(tempfile.gettempdir()) / "ai-lightroom-retouch"
    try:
        roots.append(temp_root.resolve())
    except OSError:
        pass
    return roots


def _optional_payload(batch_id: str, file_name: str) -> dict[str, Any]:
    try:
        envelope = read_batch_json(batch_id, file_name)
    except FileNotFoundError:
        return {}
    return envelope.get("payload", {})


def _load_reviews(batch_id: str) -> list[dict[str, Any]]:
    files = batch_files(batch_id)
    review_files = sorted(item["name"] for item in files if item["name"].startswith("review-pass-"))
    reviews = []
    for file_name in review_files:
        payload = _optional_payload(batch_id, file_name)
        if payload:
            payload["file_name"] = file_name
            reviews.append(payload)
    return reviews


def _load_payloads_with_prefix(batch_id: str, prefix: str) -> list[dict[str, Any]]:
    files = batch_files(batch_id)
    matching_files = sorted(item["name"] for item in files if item["name"].startswith(prefix))
    payloads = []
    for file_name in matching_files:
        payload = _optional_payload(batch_id, file_name)
        if payload:
            payload["file_name"] = file_name
            payloads.append(payload)
    return payloads


def _latest_review_by_id(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for review in reviews:
        for item in review.get("photos", []):
            result[item.get("photo_id", "")] = item
    return result


def _changed_params(params: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for key, value in params.items():
        if key not in PARAM_LABELS:
            continue
        numeric = _to_float(value)
        if numeric is None or abs(numeric) < 0.001:
            continue
        changes.append(
            {
                "key": key,
                "label": PARAM_LABELS[key],
                "value": value,
                "direction": _direction(key, numeric),
                "text": _change_sentence(key, numeric),
            }
        )
    return changes


def _direction(key: str, value: float) -> str:
    if key in {"highlights", "whites", "temperature", "texture", "clarity", "saturation", "blacks"}:
        return "negative" if value < 0 else "positive"
    return "positive" if value > 0 else "negative"


def _change_sentence(key: str, value: float) -> str:
    amount = _format_number(value)
    if key == "exposure":
        return f"{'提亮' if value > 0 else '压暗'}曝光 {amount} 档"
    if key == "contrast":
        return f"{'增加' if value > 0 else '降低'}对比度 {amount}"
    if key == "highlights":
        return f"{'压低' if value < 0 else '提高'}高光 {amount}"
    if key == "shadows":
        return f"{'提亮' if value > 0 else '压暗'}阴影 {amount}"
    if key == "whites":
        return f"{'提高' if value > 0 else '降低'}白色色阶 {amount}"
    if key == "blacks":
        return f"{'提高' if value > 0 else '压低'}黑色色阶 {amount}"
    if key == "temperature":
        return f"{'降低' if value < 0 else '提高'}白平衡色温 {amount} 开尔文"
    if key == "tint":
        return f"{'增加' if value > 0 else '降低'}色调 {amount}"
    if key == "texture":
        return f"{'柔化' if value < 0 else '增强'}纹理 {amount}"
    if key == "clarity":
        return f"{'柔化' if value < 0 else '增强'}清晰度 {amount}"
    if key == "dehaze":
        return f"{'增加' if value > 0 else '降低'}去朦胧 {amount}"
    if key == "vibrance":
        return f"{'增加' if value > 0 else '降低'}自然饱和度 {amount}"
    if key == "saturation":
        return f"{'增加' if value > 0 else '降低'}饱和度 {amount}"
    if key == "sharpening":
        return f"应用锐化 {amount}"
    if key == "noise_reduction":
        return f"应用降噪 {amount}"
    return f"{PARAM_LABELS.get(key, key)} {amount}"


def _reasons_from_metrics(metrics: dict[str, Any], params: dict[str, Any]) -> list[str]:
    reasons = []
    avg_luma = _to_float(metrics.get("avg_luma"))
    bright_ratio = _to_float(metrics.get("bright_ratio"))
    dark_ratio = _to_float(metrics.get("dark_ratio"))
    highlight_clip = _to_float(metrics.get("highlight_clip"))
    shadow_clip = _to_float(metrics.get("shadow_clip"))
    saturation = _to_float(metrics.get("avg_saturation"))
    warmth = _to_float(metrics.get("warmth"))
    sharpness = _to_float(metrics.get("sharpness"))

    if avg_luma is not None and avg_luma < 110 and _to_float(params.get("exposure", 0)) > 0:
        reasons.append("画面低于目标亮度，因此提高曝光并提亮阴影。")
    if avg_luma is not None and avg_luma > 150 and _to_float(params.get("exposure", 0)) < 0:
        reasons.append("画面已经偏亮，因此轻微降低曝光。")
    if highlight_clip is not None and highlight_clip > 0.01:
        reasons.append("检测到高光溢出，因此压低高光。")
    elif bright_ratio is not None and bright_ratio > 0.18:
        reasons.append("画面亮部面积较大，因此控制高光。")
    if shadow_clip is not None and shadow_clip > 0.02:
        reasons.append("检测到暗部死黑，因此打开阴影细节。")
    elif dark_ratio is not None and dark_ratio > 0.25:
        reasons.append("画面暗调区域较多，因此提亮阴影。")
    if warmth is not None and abs(warmth) > 35:
        reasons.append("检测到白平衡偏移，因此修正色温。")
    if saturation is not None and saturation < 30 and _to_float(params.get("vibrance", 0)) > 0:
        reasons.append("检测到饱和度偏低，因此提高自然饱和度。")
    if sharpness is not None and sharpness < 11:
        reasons.append("检测到边缘细节偏弱，因此增加锐化。")
    if not reasons:
        reasons.append("应用所选组风格，并进行少量单张校正。")
    return reasons


def _scene_counts(photos: list[dict[str, Any]], fallback_scene: Any = None) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for photo in photos:
        scene = str(photo.get("detected_scene") or fallback_scene or "auto").strip() or "auto"
        counts[scene] = counts.get(scene, 0) + 1
    if not counts and fallback_scene:
        scene = str(fallback_scene).strip() or "auto"
        counts[scene] = 0
    return [
        {"scene": scene, "label": _lookup(SCENE_LABELS, scene), "count": count}
        for scene, count in sorted(counts.items(), key=lambda item: (-item[1], _lookup(SCENE_LABELS, item[0])))
    ]


def _scene_summary(summary: dict[str, Any]) -> str:
    counts = summary.get("scene_counts") or _scene_counts(
        summary.get("photos", []),
        summary.get("scene") or summary.get("group_style", {}).get("scene"),
    )
    if not counts:
        return "未分析"
    return "、".join(f"{item['label']} {item['count']} 张" for item in counts)


def _scene_distribution_html(summary: dict[str, Any]) -> str:
    counts = summary.get("scene_counts") or []
    if not counts:
        return '<span class="muted">暂无场景分布</span>'
    items = [
        f'<span class="change"><strong>{escape(str(item["label"]))}</strong><span>{escape(str(item["count"]))} 张</span></span>'
        for item in counts
    ]
    return '<div class="changes">' + "".join(items) + "</div>"


def _advanced_changes_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict) or not plan.get("applied"):
        return []
    settings = plan.get("lightroom_settings", {})
    return _advanced_changes_from_settings(settings)


def _advanced_changes_from_settings(settings: Any) -> list[dict[str, Any]]:
    if not isinstance(settings, dict):
        return []

    changes = []
    for key, value in sorted(settings.items()):
        numeric = _to_float(value)
        if numeric is not None and abs(numeric) < 0.001:
            continue
        changes.append(
            {
                "key": key,
                "label": _advanced_setting_label(key),
                "value": value,
                "direction": "positive" if numeric is None or numeric >= 0 else "negative",
                "text": _advanced_change_sentence(key, value),
            }
        )
    return changes


def _advanced_setting_label(key: Any) -> str:
    text = str(key or "")
    if text in ADVANCED_SETTING_LABELS:
        return ADVANCED_SETTING_LABELS[text]
    for prefix, label in (
        ("SaturationAdjustment", "饱和度"),
        ("LuminanceAdjustment", "明亮度"),
        ("HueAdjustment", "色相"),
    ):
        if text.startswith(prefix):
            color = text.removeprefix(prefix)
            return f"{COLOR_LABELS.get(color, color)}{label}"
    return text or "进阶参数"


def _advanced_change_sentence(key: Any, value: Any) -> str:
    label = _advanced_setting_label(key)
    if str(key).startswith("Crop"):
        return f"Lightroom 进阶裁剪：{label} {_signed(value)}"
    if str(key).startswith("PostCropVignette"):
        return f"Lightroom 进阶暗角：{label} {_signed(value)}"
    return f"Lightroom 进阶参数：{label} {_signed(value)}"


def _advanced_batch_status(photos: list[dict[str, Any]]) -> dict[str, Any]:
    photo_count = len(photos)
    planned_photo_count = 0
    applied_photo_count = 0
    setting_count = 0
    applied_section_count = 0
    pending_section_count = 0

    for photo in photos:
        plan = photo.get("advanced_plan", {})
        suggestions = photo.get("advanced_suggestions", [])
        if not isinstance(plan, dict):
            plan = {}
        sections = plan.get("sections", []) if isinstance(plan.get("sections"), list) else []
        settings = plan.get("lightroom_settings", {}) if isinstance(plan.get("lightroom_settings"), dict) else {}
        if sections or settings or suggestions:
            planned_photo_count += 1
        if plan.get("applied"):
            applied_photo_count += 1
        setting_count += len(settings)
        for section in sections:
            if not isinstance(section, dict):
                continue
            if section.get("applied"):
                applied_section_count += 1
            else:
                pending_section_count += 1

    if applied_photo_count:
        code = "applied" if applied_photo_count == planned_photo_count else "partial"
        return {
            "code": code,
            "label": "已执行",
            "detail": f"{applied_photo_count}/{photo_count} 张执行，{setting_count} 项 Lightroom 进阶参数",
            "planned_photo_count": planned_photo_count,
            "applied_photo_count": applied_photo_count,
            "setting_count": setting_count,
            "applied_section_count": applied_section_count,
            "pending_section_count": pending_section_count,
        }
    if planned_photo_count:
        return {
            "code": "suggested",
            "label": "仅建议",
            "detail": f"{planned_photo_count}/{photo_count} 张生成进阶计划，尚未执行 Lightroom 进阶参数",
            "planned_photo_count": planned_photo_count,
            "applied_photo_count": 0,
            "setting_count": setting_count,
            "applied_section_count": applied_section_count,
            "pending_section_count": pending_section_count,
        }
    return {
        "code": "none",
        "label": "未启用",
        "detail": "当前批次没有进阶计划",
        "planned_photo_count": 0,
        "applied_photo_count": 0,
        "setting_count": 0,
        "applied_section_count": 0,
        "pending_section_count": 0,
    }


def _retouch_batch_status(
    pixel_reports: list[dict[str, Any]],
    photoshop_reports: list[dict[str, Any]],
    export_report: dict[str, Any],
    photos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if photoshop_reports:
        completed = 0
        failed = 0
        pending = 0
        operation_count = 0
        mask_count = 0
        for report in photoshop_reports:
            status = str(report.get("status") or _nested_get(report, ["job", "status"]) or "").lower()
            if status in {"completed", "ok", "done"}:
                completed += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1
            operations = report.get("operations_planned", [])
            if isinstance(operations, list):
                operation_count += len(operations)
            masks = report.get("mask_assets", [])
            if isinstance(masks, list):
                mask_count += len(masks)
        label = "Photoshop 有失败" if failed else ("Photoshop 已完成" if completed == len(photoshop_reports) else "Photoshop 待执行")
        return {
            "code": "failed" if failed else ("completed" if completed == len(photoshop_reports) else "pending"),
            "label": label,
            "detail": f"{len(photoshop_reports)} 张，完成 {completed}，待执行 {pending}，失败 {failed}，计划 {operation_count} 项，蒙版 {mask_count} 个",
        }

    if pixel_reports:
        ok_count = sum(1 for report in pixel_reports if str(report.get("status") or "").lower() == "ok")
        applied_count = 0
        for report in pixel_reports:
            operations = report.get("operations_applied", [])
            if isinstance(operations, list):
                applied_count += len(operations)
        return {
            "code": "completed" if ok_count == len(pixel_reports) else "partial",
            "label": "本地像素精修",
            "detail": f"{ok_count}/{len(pixel_reports)} 张成功，应用 {applied_count} 项局部操作",
        }

    if export_report:
        label, detail = _export_status(export_report)
        return {"code": "export", "label": label, "detail": detail}

    planned_photos = 0
    planned_operations = 0
    for photo in photos or []:
        local_analysis = photo.get("local_analysis", {}) if isinstance(photo.get("local_analysis"), dict) else {}
        pixel_retouch = local_analysis.get("pixel_retouch", {}) if isinstance(local_analysis.get("pixel_retouch"), dict) else {}
        operations = local_analysis.get("operations", [])
        if pixel_retouch.get("available") or operations:
            planned_photos += 1
        if isinstance(operations, list):
            planned_operations += len(operations)
    if planned_photos:
        return {
            "code": "planned",
            "label": "待执行精修",
            "detail": f"已生成 {planned_photos} 张/{planned_operations} 项局部精修计划，等待 Lightroom 导出高质量源图并执行",
        }

    return {"code": "none", "label": "未进入精修", "detail": "等待 Lightroom 导出或像素/Photoshop 精修"}


def _summary_cards(summary: dict[str, Any]) -> str:
    latest_review = summary.get("latest_review", {})
    passed = latest_review.get("passed")
    review_status = "尚未审核" if passed is None else ("通过" if passed else "需要修正")
    score = latest_review.get("score", "-")
    scene = _scene_summary(summary)
    aesthetic = _lookup(AESTHETIC_LABELS, summary.get("aesthetic") or summary.get("group_style", {}).get("aesthetic"))
    edit_level = _lookup(EDIT_LEVEL_LABELS, summary.get("edit_level") or summary.get("group_style", {}).get("edit_level"))
    ai_source = _ai_source_summary(summary.get("ai_status", {}))
    export_status, export_count = _export_status(summary.get("export_report", {}))
    suggestion = str(summary.get("user_suggestion") or "").strip()
    suggestion_status = "已填写" if suggestion else "无"
    advanced_status = summary.get("advanced_status", {})
    retouch_status = summary.get("retouch_status", {})
    return f"""
<div class="grid">
  <div class="panel"><div class="label">照片场景</div><div class="value">{escape(scene)}</div></div>
  <div class="panel"><div class="label">审美风格</div><div class="value">{escape(aesthetic)}</div></div>
  <div class="panel"><div class="label">处理层级</div><div class="value">{escape(edit_level)}</div></div>
  <div class="panel"><div class="label">AI 来源</div><div class="value">{escape(ai_source)}</div></div>
  <div class="panel"><div class="label">用户建议</div><div class="value">{escape(suggestion_status)}</div></div>
  <div class="panel"><div class="label">进阶执行</div><div class="value">{escape(str(advanced_status.get("label") or "未启用"))}</div><div class="small muted">{escape(str(advanced_status.get("detail") or ""))}</div></div>
  <div class="panel"><div class="label">精修流程</div><div class="value">{escape(str(retouch_status.get("label") or "未进入精修"))}</div><div class="small muted">{escape(str(retouch_status.get("detail") or ""))}</div></div>
  <div class="panel"><div class="label">照片数</div><div class="value">{summary.get("photo_count", 0)}</div></div>
  <div class="panel"><div class="label">最新审核</div><div class="value">{escape(review_status)}</div></div>
  <div class="panel"><div class="label">评分</div><div class="value">{escape(str(score))}</div></div>
  <div class="panel"><div class="label">最终导出</div><div class="value">{escape(export_status)}</div><div class="small muted">{escape(export_count)}</div></div>
</div>
"""


def _export_status(report: dict[str, Any]) -> tuple[str, str]:
    mode = str(report.get("mode") or "")
    if mode == "pixel-retouch-staged":
        return "待人工确认", f"已生成 {report.get('staged_count', 0)} 张，已导入 {report.get('imported_count', 0)} 张"
    if mode == "pixel-retouch-finalized":
        return "像素精修已导出", f"{report.get('exported_count', 0)} 张"
    if mode == "pixel-retouch-direct":
        return "像素精修已导出", f"{report.get('exported_count', 0)} 张"
    if mode == "photoshop-retouch-staged":
        return "Photoshop 精修待确认", f"已生成 {report.get('completed_count', report.get('staged_count', 0))} 张，待执行 {report.get('pending_count', 0)} 张，已导入 {report.get('imported_count', 0)} 张"
    if mode == "photoshop-retouch-finalized":
        return "Photoshop 精修已导出", f"{report.get('exported_count', 0)} 张"
    if mode == "photoshop-retouch-direct":
        return "Photoshop 精修已导出", f"{report.get('exported_count', 0)} 张"
    if mode == "develop-only":
        return "已导出", f"{report.get('exported_count', 0)} 张"
    if report:
        return "已记录", str(report.get("export_dir") or "")
    return "未导出", ""


def _batch_status_html(status: dict[str, Any]) -> str:
    if not status:
        return '<span class="muted">暂无状态</span>'
    code = str(status.get("code") or "")
    class_name = "good" if code in {"applied", "completed", "export"} else ("warn" if code in {"partial", "suggested", "pending", "failed"} else "")
    detail = str(status.get("detail") or "").strip()
    detail_html = f'<div class="small muted">{escape(detail)}</div>' if detail else ""
    return f'<span class="pill {class_name}">{escape(str(status.get("label") or "未知"))}</span>{detail_html}'


def _user_suggestion_html(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"""
  <div class="section-title">用户建议</div>
  <div>{escape(text)}</div>
"""


def _group_summary(summary: dict[str, Any]) -> str:
    group_style = summary.get("group_style", {})
    base_params = group_style.get("base_params", {})
    if not group_style:
        return f"""
<div class="panel">
  <div class="muted">这个批次还没有保存分析结果。</div>
  {_user_suggestion_html(summary.get("user_suggestion"))}
  <div class="section-title">场景分布</div>
  {_scene_distribution_html(summary)}
  <div class="section-title">进阶执行状态</div>
  {_batch_status_html(summary.get("advanced_status", {}))}
  <div class="section-title">精修流程状态</div>
  {_batch_status_html(summary.get("retouch_status", {}))}
</div>
"""
    scene = _lookup(SCENE_LABELS, group_style.get("scene"))
    aesthetic = _lookup(AESTHETIC_LABELS, group_style.get("aesthetic"))
    edit_level = _lookup(EDIT_LEVEL_LABELS, group_style.get("edit_level"))
    skin_target = _lookup(SKIN_TARGET_LABELS, group_style.get("skin_tone_target"))
    contrast_level = _lookup(CONTRAST_LABELS, group_style.get("contrast_level"))
    ai_status_html = _ai_status_html(summary.get("ai_status", {}))
    user_suggestion_html = _user_suggestion_html(summary.get("user_suggestion"))
    scene_distribution_html = _scene_distribution_html(summary)
    advanced_status_html = _batch_status_html(summary.get("advanced_status", {}))
    retouch_status_html = _batch_status_html(summary.get("retouch_status", {}))
    return f"""
<div class="panel">
  <div class="grid">
    <div><div class="label">场景</div><div>{escape(scene)}</div></div>
    <div><div class="label">审美</div><div>{escape(aesthetic)}</div></div>
    <div><div class="label">层级</div><div>{escape(edit_level)}</div></div>
    <div><div class="label">肤色目标</div><div>{escape(skin_target)}</div></div>
    <div><div class="label">对比度倾向</div><div>{escape(contrast_level)}</div></div>
  </div>
  <div class="section-title">场景分布</div>
  {scene_distribution_html}
  <div class="section-title">AI 来源</div>
  {ai_status_html}
  {user_suggestion_html}
  <div class="section-title">进阶执行状态</div>
  {advanced_status_html}
  <div class="section-title">精修流程状态</div>
  {retouch_status_html}
  <div class="section-title">整组基础修改</div>
  {_changes_html(_changed_params(base_params))}
</div>
"""


def _preview_compare_grid(summary: dict[str, Any], return_url: str | None = None) -> str:
    photos = [
        photo
        for photo in summary.get("photos", [])
        if photo.get("before_preview_url") or photo.get("basic_preview_url") or photo.get("retouch_preview_url") or photo.get("after_preview_url")
    ]
    if not photos:
        return '<div class="panel muted">还没有可显示的修图预览。完成 AI 审核后会显示基础修后图；执行像素或 Photoshop 精修后会显示精修后图。</div>'

    cards = []
    for photo in photos:
        before = _preview_image_html(photo.get("before_preview_url"), "修图前", return_url)
        retouch_url = photo.get("retouch_preview_url")
        basic_url = photo.get("basic_preview_url") or (photo.get("after_preview_url") if not retouch_url else "")
        basic = _preview_image_html(basic_url, "基础修后", return_url)
        stages = [
            f'<div><div class="preview-caption">修图前</div>{before}</div>',
            f'<div><div class="preview-caption">基础修后</div>{basic}</div>',
        ]
        if retouch_url:
            retouch = _preview_image_html(retouch_url, "精修后", return_url)
            stages.append(f'<div><div class="preview-caption">精修后</div>{retouch}</div>')
        detected = _lookup(SCENE_LABELS, photo.get("detected_scene"))
        cards.append(
            '<div class="compare-card">'
            f'<strong>{escape(str(photo.get("file_name", "")))}</strong>'
            f'<div class="small muted">单张场景：{escape(detected)}</div>'
            '<div class="compare-images">'
            + "".join(stages) +
            "</div>"
            "</div>"
        )
    return '<div class="compare-grid">' + "".join(cards) + "</div>"


def _preview_image_html(url: Any, label: str, return_url: str | None = None) -> str:
    if not url:
        return f'<div class="preview-frame"><span class="muted">暂无{escape(label)}预览</span></div>'
    raw_url = str(url)
    view_url = _image_view_url(raw_url, return_url)
    safe_url = escape(raw_url, quote=True)
    safe_view_url = escape(view_url, quote=True)
    safe_label = escape(label)
    return f'<div class="preview-frame"><a href="{safe_view_url}" target="_blank" rel="noopener"><img src="{safe_url}" alt="{safe_label}"></a></div>'


def _image_view_url(image_url: str, return_url: str | None = None) -> str:
    view_url = image_url.replace("/dashboard/image?", "/dashboard/image-view?", 1)
    if return_url:
        view_url += "&return_to=" + quote(return_url, safe="")
    return view_url


def _safe_dashboard_return_url(value: str | None) -> str:
    text = str(value or "").strip()
    if text == "/dashboard" or text.startswith("/dashboard/") or text.startswith("/dashboard?"):
        return text
    return "/dashboard/runs"


def _ai_source_summary(status: dict[str, Any]) -> str:
    if not status:
        return "规则模式（旧批次）"
    if status.get("used_external_ai"):
        source = SOURCE_LABELS.get(str(status.get("source") or ""), str(status.get("source") or "外部 AI"))
        wire_api = str(status.get("wire_api") or "").strip()
        model = str(status.get("model") or "").strip()
        parts = [source]
        if wire_api:
            parts.append(wire_api)
        if model:
            parts.append(model)
        return " / ".join(parts)
    if status.get("requested_external_ai"):
        return "外部 AI 失败，规则回退"
    return "本地规则"


def _ai_status_html(status: dict[str, Any]) -> str:
    label = _ai_source_summary(status)
    if not status:
        return '<span class="pill">规则模式（旧批次）</span>'
    class_name = "good" if status.get("used_external_ai") else ("warn" if status.get("requested_external_ai") else "")
    message = _zh_text(status.get("message"), "外部 AI 已完成本批次分析。")
    count = ""
    if status.get("used_external_ai"):
        count = f'<div class="small muted">已由外部 AI 修正 {escape(str(status.get("applied_photo_count", 0)))} / {escape(str(status.get("photo_count", 0)))} 张。</div>'
    endpoint = str(status.get("endpoint") or "")
    endpoint_html = f'<div class="small muted">请求地址：{escape(endpoint)}</div>' if endpoint else ""
    message_html = f'<div class="small muted">{escape(message)}</div>' if message else ""
    return f'<span class="pill {class_name}">{escape(label)}</span>{count}{message_html}{endpoint_html}'


def _photo_ai_source_label(photo: dict[str, Any]) -> str:
    if photo.get("ai_source") == "external_ai":
        return "外部 AI"
    return "本地规则"


def _review_ai_source_label(status: dict[str, Any]) -> str:
    if status.get("used_external_ai"):
        return "外部 AI"
    if status.get("requested_external_ai"):
        return "外部 AI 失败，规则回退"
    return "本地规则"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _zh_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    exact = {
        "AI crop/recompose": "AI 构图/裁剪",
        "original": "原比例",
    }
    if text in exact:
        return exact[text]
    return text if _has_cjk(text) else fallback


def _zh_items(values: Any, fallback: str, limit: int = 6) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result = [_zh_text(item, fallback) for item in values if str(item).strip()]
    unique: list[str] = []
    for item in result:
        if item not in unique:
            unique.append(item)
    return unique[:limit]


def _zh_section_name(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "color_mixer": "混色器",
        "tone_curve": "曲线",
        "color_grading": "色彩分级",
        "crop_recompose": "裁剪/重构图",
        "local_region_analysis": "局部区域分析",
        "pixel_retouch_plan": "像素精修计划",
        "mask": "蒙版计划",
        "masks": "蒙版计划",
    }
    return mapping.get(text, _zh_text(text, "AI 进阶调整"))


def _zh_aspect(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "original": "原比例",
        "free": "自由比例",
        "1:1": "1:1",
        "4:5": "4:5",
        "3:2": "3:2",
        "16:9": "16:9",
    }
    return mapping.get(text, _zh_text(text, "原比例"))


def _zh_issue_label(issue: Any) -> str:
    text = str(issue or "").strip()
    if not text:
        return "需要轻微微调"
    key = text.lower().replace(" ", "_").replace("-", "_")
    if key in ISSUE_LABELS:
        return ISSUE_LABELS[key]
    if text in ISSUE_LABELS:
        return ISSUE_LABELS[text]
    return text if _has_cjk(text) else "需要轻微微调"


def _ai_notes_html(notes: list[str]) -> str:
    items = _zh_items(notes, "AI 已根据预览图完成判断。", limit=4)
    if not items:
        return ""
    return '<ul class="reason-list small">' + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _photo_modifications_html(photo: dict[str, Any]) -> str:
    basic_changes = photo.get("changed_params", [])
    advanced_changes = photo.get("advanced_changes") or _advanced_changes_from_plan(photo.get("advanced_plan", {}))
    parts = []
    if basic_changes:
        parts.append('<div class="small muted">基础参数</div>')
        parts.append(_changes_html(basic_changes))
    if advanced_changes:
        parts.append('<div class="small muted" style="margin-top:8px">进阶参数</div>')
        parts.append(_changes_html(advanced_changes))
    if not parts:
        return '<span class="muted">没有参数变化</span>'
    return "".join(parts)


def _photo_changes_table(summary: dict[str, Any]) -> str:
    photos = summary.get("photos", [])
    if not photos:
        return '<div class="panel muted">还没有单张修图方案。</div>'

    rows = []
    for photo in photos:
        ai_source = _photo_ai_source_label(photo)
        ai_notes = _ai_notes_html(photo.get("ai_notes", []))
        photo_suggestion = str(photo.get("photo_user_suggestion") or "").strip()
        suggestion_html = f'<div class="small muted">单张建议：{escape(photo_suggestion)}</div>' if photo_suggestion else ""
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(photo.get('file_name', '')))}</strong><div class=\"small muted\">{escape(str(photo.get('photo_id', '')))}</div><div class=\"small muted\">单张场景：{escape(_lookup(SCENE_LABELS, photo.get('detected_scene')))}</div><div class=\"small muted\">AI 来源：{escape(ai_source)}</div>{suggestion_html}{ai_notes}</td>"
            f"<td>{_photo_modifications_html(photo)}</td>"
            f"<td>{_reasons_html(photo.get('reasons', []))}</td>"
            f"<td>{_crop_suggestion_html(photo.get('crop_suggestion', {}))}</td>"
            f"<td>{_advanced_plan_html(photo.get('advanced_plan', {}), photo.get('advanced_suggestions', []))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>照片</th><th>修改明细</th><th>修改原因</th><th>构图/裁剪</th><th>进阶执行/建议</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _review_table(summary: dict[str, Any]) -> str:
    latest_review = summary.get("latest_review", {})
    photos = latest_review.get("photos", [])
    if not photos:
        return '<div class="panel muted">还没有审核记录。</div>'

    rows = []
    file_by_id = {item.get("photo_id"): item.get("file_name") for item in summary.get("photos", [])}
    review_source = _review_ai_source_label(latest_review.get("ai_status", {}))
    for item in photos:
        issues = item.get("issues", [])
        deltas = item.get("deltas", {})
        notes = _ai_notes_html(item.get("ai_notes", []))
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(file_by_id.get(item.get('photo_id'), item.get('photo_id'))))}</strong></td>"
            f"<td>{_status_pill(bool(item.get('passed')), item.get('score'))}<div class=\"small muted\">审核来源：{escape(review_source)}</div>{notes}</td>"
            f"<td>{_issues_html(issues)}</td>"
            f"<td>{_changes_html(_changed_params(deltas))}</td>"
            f"<td>{_metrics_delta_html(item.get('metrics', {}).get('delta', {}))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>照片</th><th>状态</th><th>问题</th><th>修正量</th><th>校样变化</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _changes_html(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return '<span class="muted">没有参数变化</span>'
    items = []
    for change in changes:
        direction = "positive" if change.get("direction") == "positive" else "negative"
        items.append(
            f'<span class="change"><strong>{escape(change["label"])}</strong> '
            f'<span class="{direction}">{escape(_signed(change["value"]))}</span>'
            f'<span class="muted">{escape(change["text"])}</span></span>'
        )
    return '<div class="changes">' + "".join(items) + "</div>"


def _reasons_html(reasons: list[str]) -> str:
    items = _zh_items(reasons, "根据画面指标生成基础参数。")
    return '<ul class="reason-list">' + "".join(f"<li>{escape(reason)}</li>" for reason in items) + "</ul>"


def _advanced_suggestions_html(suggestions: list[str]) -> str:
    items = _zh_items(suggestions, "可使用进阶功能继续微调主体、背景和色彩层次。")
    if not items:
        return '<span class="muted">未启用进阶建议</span>'
    return '<ul class="reason-list">' + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _advanced_settings_html(settings: Any, empty_text: str = "") -> str:
    changes = _advanced_changes_from_settings(settings)
    if not changes:
        return f'<span class="muted">{escape(empty_text)}</span>' if empty_text else ""
    return _changes_html(changes)


def _advanced_sections_html(sections: Any) -> str:
    if not isinstance(sections, list) or not sections:
        return ""
    parts = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        name = _zh_section_name(section.get("name"))
        applied = bool(section.get("applied"))
        state = "已执行" if applied else "仅记录/待外部精修"
        class_name = "good" if applied else "warn"
        settings_html = _advanced_settings_html(section.get("settings", {}))
        notes = _zh_items(section.get("notes", []), "AI 已记录该项进阶调整。", limit=4)
        notes_html = _reasons_html(notes) if notes else ""
        if not settings_html and not notes_html:
            settings_html = '<div class="small muted">无可直接写入 Lightroom 的参数</div>'
        parts.append(
            '<div style="margin-top:8px">'
            f'<span class="pill {class_name}">{escape(state)}</span>'
            f'<strong>{escape(name)}</strong>'
            f'{settings_html}'
            f'{notes_html}'
            "</div>"
        )
    return "".join(parts)


def _advanced_limitations_html(limitations: Any) -> str:
    items = _zh_items(limitations, "部分进阶修改需要外部像素精修或 Photoshop 执行。", limit=3)
    if not items:
        return ""
    return '<div class="small muted" style="margin-top:8px">限制：' + escape("；".join(items)) + "</div>"


def _advanced_plan_html(plan: dict[str, Any], suggestions: list[str]) -> str:
    if not plan:
        return _advanced_suggestions_html(suggestions)

    sections = plan.get("sections", [])
    clean_sections = [item for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []
    applied_sections = [_zh_section_name(item.get("name")) for item in clean_sections if item.get("applied")]
    pending_sections = [_zh_section_name(item.get("name")) for item in clean_sections if not item.get("applied")]
    settings_html = _advanced_settings_html(plan.get("lightroom_settings", {}))
    sections_html = _advanced_sections_html(clean_sections)
    limitations_html = _advanced_limitations_html(plan.get("limitations", []))

    if plan.get("applied"):
        parts = ['<span class="pill good">已执行进阶修改</span>']
        if applied_sections:
            parts.append(f'<div class="small">已应用：{escape("、".join(applied_sections))}</div>')
        if pending_sections:
            parts.append(f'<div class="small muted">仅记录：{escape("、".join(pending_sections))}</div>')
        if settings_html:
            parts.append('<div class="small muted" style="margin-top:8px">写入 Lightroom 的进阶参数</div>')
            parts.append(settings_html)
        if sections_html:
            parts.append(sections_html)
        if limitations_html:
            parts.append(limitations_html)
        return "".join(parts)

    parts = ['<span class="pill warn">仅生成进阶建议</span>']
    if clean_sections:
        parts.append(f'<div class="small">建议项目：{escape("、".join(_zh_section_name(item.get("name")) for item in clean_sections))}</div>')
    if sections_html:
        parts.append(sections_html)
    if suggestions:
        parts.append(_advanced_suggestions_html(suggestions))
    if limitations_html:
        parts.append(limitations_html)
    return "".join(parts)


def _crop_suggestion_html(suggestion: dict[str, Any]) -> str:
    if not suggestion:
        return '<span class="muted">暂无裁剪建议</span>'
    enabled = suggestion.get("enabled")
    aspect = _zh_aspect(suggestion.get("aspect_ratio", "原比例"))
    fallback = "AI 建议裁剪以强化主体并减少边缘干扰。" if enabled else "AI 判断当前构图可以保留原比例。"
    reason = _zh_text(suggestion.get("reason", ""), fallback)
    state = "建议裁剪" if enabled else "保持原比例"
    return (
        f'<span class="pill {"warn" if enabled else "good"}">{escape(state)}</span>'
        f'<div class="small">比例：{escape(str(aspect))}</div>'
        f'<div class="small muted">{escape(str(reason))}</div>'
    )


def _issues_html(issues: list[str]) -> str:
    if not issues:
        return '<span class="pill good">无问题</span>'
    return "".join(f'<span class="pill warn">{escape(_zh_issue_label(issue))}</span>' for issue in issues)


def _status_pill(passed: bool, score: Any) -> str:
    label = "通过" if passed else "需修正"
    class_name = "good" if passed else "warn"
    return f'<span class="pill {class_name}">{label}</span><div class="small muted">评分 {escape(str(score))}</div>'


def _metrics_delta_html(delta: dict[str, Any]) -> str:
    if not delta:
        return '<span class="muted">没有校样指标</span>'
    items = []
    for key in ["avg_luma", "highlight_clip", "shadow_clip", "avg_saturation", "warmth"]:
        if key in delta:
            items.append(f"{METRIC_LABELS.get(key, key)} {_signed(delta[key])}")
    return "<br>".join(escape(item) for item in items)


def _batch_ai_source_label(batch_id: str) -> str:
    analyze = _optional_payload(batch_id, "analyze.json")
    return _ai_source_summary(analyze.get("ai_status", {}) if analyze else {})


def _url_segment(value: Any) -> str:
    return quote(str(value), safe="")


def _dashboard_run_url(batch_id: Any, *parts: Any) -> str:
    segments = [_url_segment(batch_id), *[_url_segment(part) for part in parts]]
    return "/dashboard/runs/" + "/".join(segments)


def _runs_table(batches: list[dict[str, Any]]) -> str:
    if not batches:
        return '<div class="panel muted">还没有批次记录。</div>'
    rows = []
    for item in batches:
        raw_batch_id = str(item["batch_id"])
        batch_id = escape(raw_batch_id)
        batch_url = _dashboard_run_url(raw_batch_id)
        edit_summary_url = _dashboard_run_url(raw_batch_id, "edit-summary")
        ai_source = _batch_ai_source_label(raw_batch_id)
        rows.append(
            "<tr>"
            f'<td><a href="{batch_url}">{batch_id}</a></td>'
            f"<td>{escape(item['updated_at'])}</td>"
            f"<td>{escape(ai_source)}</td>"
            f"<td>{item.get('photo_count') or item['file_count']}</td>"
            f"<td>{escape(', '.join(item['files'][:4]))}</td>"
            f'<td><a href="{edit_summary_url}">修图说明</a></td>'
            "</tr>"
        )
    return "<table><thead><tr><th>批次编号</th><th>更新时间（北京时间）</th><th>AI 来源</th><th>照片数</th><th>数据文件</th><th>查看</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _files_table(batch_id: str, files: list[dict[str, Any]]) -> str:
    if not files:
        return '<div class="panel muted">这个批次还没有数据文件。</div>'
    rows = []
    for item in files:
        raw_file_name = str(item["name"])
        file_name = escape(raw_file_name)
        file_url = _dashboard_run_url(batch_id, raw_file_name)
        rows.append(
            "<tr>"
            f'<td><a href="{file_url}">{file_name}</a></td>'
            f"<td>{item['size']}</td>"
            f"<td>{escape(item['updated_at'])}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>文件</th><th>大小</th><th>更新时间（北京时间）</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _events_table(events: list[dict[str, Any]]) -> str:
    if not events:
        return '<div class="panel muted">还没有事件日志。</div>'
    rows = []
    for item in events:
        event = EVENT_LABELS.get(str(item.get("event", "")), str(item.get("event", "")))
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('time', '')))}</td>"
            f"<td>{escape(event)}</td>"
            f"<td>{escape(str(item.get('batch_id', '')))}</td>"
            f"<td>{escape(str(item.get('file', '')))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>时间（北京时间）</th><th>事件</th><th>批次</th><th>文件</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _config_test_result_html(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    passed = bool(result.get("passed"))
    class_name = "good" if passed else "warn"
    status = "检测成功" if passed else "检测失败"
    fields = [
        ("接口类型", result.get("wire_api", "-")),
        ("模型", result.get("model", "-")),
        ("HTTP 状态", result.get("http_status", "-")),
        ("耗时", f"{result.get('latency_ms')} ms" if result.get("latency_ms") is not None else "-"),
        ("请求地址", result.get("endpoint", "-")),
    ]
    warnings = result.get("warnings") or []
    warning_html = "".join(f'<div class="small muted">{escape(str(item))}</div>' for item in warnings)
    details = "".join(
        f'<div><div class="label">{escape(label)}</div><div>{escape(str(value or "-"))}</div></div>'
        for label, value in fields
    )
    sample = result.get("sample")
    sample_html = f'<div class="small muted" style="margin-top:8px">返回片段：{escape(str(sample))}</div>' if sample else ""
    attempts = result.get("attempts") or []
    attempts_html = _config_attempts_html(attempts)
    return f"""
<div style="border-top:1px solid #d9e2ef; margin-top:14px; padding-top:14px">
  <span class="pill {class_name}">{status}</span>
  <div class="small" style="margin-top:6px">{escape(str(result.get("message", "")))}</div>
  {warning_html}
  <div class="grid" style="margin-top:10px">{details}</div>
  {sample_html}
  {attempts_html}
</div>
"""


def _config_attempts_html(attempts: list[dict[str, Any]]) -> str:
    if not attempts or len(attempts) <= 1:
        return ""
    rows = []
    for item in attempts:
        state = "通过" if item.get("passed") else "失败"
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('wire_api', '-')))}</td>"
            f"<td>{escape(str(item.get('http_status') or '-'))}</td>"
            f"<td>{escape(str(item.get('endpoint') or '-'))}</td>"
            f"<td>{escape(state)}</td>"
            "</tr>"
        )
    return (
        '<div class="section-title">自动检测尝试</div>'
        "<table><thead><tr><th>接口类型</th><th>HTTP</th><th>请求地址</th><th>结果</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _codex_reference_html(codex: dict[str, Any]) -> str:
    if not codex:
        return ""
    fields = [
        ("提供商", codex.get("provider", "-")),
        ("接口地址", codex.get("base_url", "-")),
        ("接口类型", codex.get("wire_api", "-")),
        ("默认模型", codex.get("model", "-")),
        ("审核模型", codex.get("review_model", "-")),
    ]
    details = "".join(
        f'<div><div class="label">{escape(label)}</div><div>{escape(str(value or "-"))}</div></div>'
        for label, value in fields
    )
    auth_note = "Codex 使用自己的认证体系；这里不会读取或复用 Codex 的认证密钥。"
    if codex.get("requires_openai_auth"):
        auth_note = "Codex 配置标记为需要 OpenAI 认证；本系统仍需要你在上方单独填写 API Key。"
    return f"""
<h2 class="section-title">Codex 配置参考</h2>
<div class="panel">
  <div class="grid">{details}</div>
  <div class="small muted" style="margin-top:10px">{escape(auth_note)}</div>
</div>
"""


def _option(value: str, label: str, selected: str) -> str:
    marker = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{marker}>{escape(label)}</option>'


def _style_label(style: Any) -> str:
    if style is None:
        return "-"
    return STYLE_LABELS.get(str(style), str(style))


def _lookup(labels: dict[str, str], value: Any) -> str:
    if value is None:
        return "-"
    return labels.get(str(value), str(value))


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float) -> str:
    if abs(value) < 1:
        return f"{value:+.2f}"
    return f"{value:+.0f}"


def _signed(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return str(value)
    return _format_number(numeric)
