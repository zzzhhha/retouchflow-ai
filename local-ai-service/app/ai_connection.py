from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from .config import AIConfig, load_ai_config, normalize_base_url, normalize_wire_api


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def test_ai_config(config: AIConfig | None = None, timeout: float = 20) -> dict[str, Any]:
    config = config or load_ai_config()
    wire_api = normalize_wire_api(config.wire_api)
    started = time.perf_counter()
    result = _base_result(config, wire_api)

    validation_error = _validation_error(config)
    if validation_error:
        result["message"] = validation_error
        return result

    candidates = _wire_api_candidates(wire_api)
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        attempt = _run_prompt(config, candidate, "请只回复 OK。", 8, timeout, started)
        attempts.append(
            {
                "wire_api": candidate,
                "endpoint": attempt.get("endpoint", ""),
                "http_status": attempt.get("http_status"),
                "passed": attempt.get("passed", False),
                "message": attempt.get("message", ""),
            }
        )
        if attempt.get("passed"):
            attempt["wire_api"] = candidate
            attempt["attempts"] = attempts
            return attempt
        if attempt.get("cloudflare_error"):
            attempt["wire_api"] = candidate
            attempt["attempts"] = attempts
            return attempt

    result.update(attempts[-1] if attempts else {})
    result["wire_api"] = wire_api
    result["attempts"] = attempts
    if wire_api == "openai_relay":
        tried = "、".join(item["wire_api"] for item in attempts)
        result["message"] = f"中转站自动检测失败，已尝试：{tried}。最后错误：{result.get('message', '')}"
    return result


def call_ai_text(
    config: AIConfig,
    prompt: str,
    max_tokens: int = 1600,
    timeout: float = 60,
    image_urls: list[str] | None = None,
) -> dict[str, Any]:
    wire_api = normalize_wire_api(config.wire_api)
    started = time.perf_counter()
    result = _base_result(config, wire_api)

    validation_error = _validation_error(config)
    if validation_error:
        result["message"] = validation_error
        return result

    candidates = _wire_api_candidates(wire_api)
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        attempt = _run_prompt(config, candidate, prompt, max_tokens, timeout, started, image_urls or [])
        attempts.append(
            {
                "wire_api": candidate,
                "endpoint": attempt.get("endpoint", ""),
                "http_status": attempt.get("http_status"),
                "passed": attempt.get("passed", False),
                "message": attempt.get("message", ""),
            }
        )
        if attempt.get("passed"):
            attempt["wire_api"] = candidate
            attempt["attempts"] = attempts
            return attempt
        if attempt.get("cloudflare_error"):
            attempt["wire_api"] = candidate
            attempt["attempts"] = attempts
            return attempt

    result.update(attempts[-1] if attempts else {})
    result["wire_api"] = wire_api
    result["attempts"] = attempts
    if wire_api == "openai_relay":
        tried = "、".join(item["wire_api"] for item in attempts)
        result["message"] = f"中转站 AI 调用失败，已尝试：{tried}。最后错误：{result.get('message', '')}"
    return result


def _base_result(config: AIConfig, wire_api: str) -> dict[str, Any]:
    return {
        "passed": False,
        "provider": config.provider,
        "base_url": config.public_base_url,
        "model": config.model,
        "wire_api": wire_api,
        "configured": config.configured,
        "masked_api_key": config.masked_api_key,
        "warnings": list(config.warnings),
        "http_status": None,
        "latency_ms": None,
        "endpoint": "",
        "message": "",
        "sample": "",
        "text": "",
        "attempts": [],
    }


def _run_prompt(
    config: AIConfig,
    wire_api: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
    started: float,
    image_urls: list[str] | None = None,
) -> dict[str, Any]:
    result = _base_result(config, wire_api)
    try:
        endpoint = _endpoint_url(config, wire_api)
    except ValueError as exc:
        result["message"] = str(exc)
        return result

    result["endpoint"] = endpoint
    request = _request_for(config, endpoint, wire_api, prompt, max_tokens, image_urls or [])

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65536)
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        raw = exc.read(4096)
        result["http_status"] = exc.code
        result["latency_ms"] = _elapsed_ms(started)
        result["message"] = _http_error_message(exc.code, raw, config)
        result["cloudflare_error"] = _is_cloudflare_1010_payload(raw)
        return result
    except urllib.error.URLError as exc:
        result["latency_ms"] = _elapsed_ms(started)
        result["message"] = _sanitize(f"连接失败：{exc.reason}", config)
        return result
    except TimeoutError:
        result["latency_ms"] = _elapsed_ms(started)
        result["message"] = "连接超时，请检查接口地址、网络或代理。"
        return result

    result["http_status"] = status
    result["latency_ms"] = _elapsed_ms(started)
    payload = _json_or_text(raw)
    text = _text_from_payload(payload)
    result["text"] = text
    result["sample"] = text[:160]
    if 200 <= status < 300:
        result["passed"] = True
        result["message"] = "AI 配置检测成功，接口可以正常返回结果。"
    else:
        result["message"] = _sanitize(f"接口返回非成功状态：HTTP {status}", config)
    return result


def _wire_api_candidates(wire_api: str) -> list[str]:
    if wire_api == "openai_relay":
        return ["chat_completions", "completions", "legacy_completions", "responses"]
    return [wire_api]


def _validation_error(config: AIConfig) -> str:
    if not config.enabled:
        return "外部 AI 未启用，请先勾选启用。"
    if config.provider == "mock":
        return "当前是规则模式，不会调用外部 AI。"
    if not config.api_key:
        return "缺少 API Key。"
    if not config.model:
        return "缺少模型名称。"
    if config.provider == "custom" and not config.base_url:
        return "自定义接口必须填写接口地址。"
    return ""


def _endpoint_url(config: AIConfig, wire_api: str) -> str:
    base_url = normalize_base_url(config.base_url)
    if not base_url:
        base_url = DEFAULT_OPENAI_BASE_URL
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("接口地址必须以 http:// 或 https:// 开头。")

    clean = base_url.rstrip("/")
    if clean.endswith("/responses") or clean.endswith("/chat/completions") or clean.endswith("/completions"):
        return clean
    if wire_api == "completions":
        return f"{clean}/completions"
    if wire_api == "legacy_completions":
        return f"{clean}/engines/{quote(config.model, safe='')}/completions"
    if wire_api == "chat_completions":
        return f"{clean}/chat/completions"
    return f"{clean}/responses"


def _request_for(
    config: AIConfig,
    endpoint: str,
    wire_api: str,
    prompt: str,
    max_tokens: int,
    image_urls: list[str] | None = None,
) -> urllib.request.Request:
    image_urls = image_urls or []
    if wire_api == "legacy_completions":
        body = {
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
    elif wire_api == "completions":
        body = {
            "model": config.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
    elif wire_api == "chat_completions":
        content: str | list[dict[str, Any]]
        if image_urls:
            content = [{"type": "text", "text": prompt}]
            content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
        else:
            content = prompt
        body = {
            "model": config.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
    else:
        input_payload: str | list[dict[str, Any]]
        if image_urls:
            content = [{"type": "input_text", "text": prompt}]
            content.extend({"type": "input_image", "image_url": url} for url in image_urls)
            input_payload = [{"role": "user", "content": content}]
        else:
            input_payload = prompt
        body = {
            "model": config.model,
            "input": input_payload,
            "max_output_tokens": max_tokens,
        }

    return urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-Retouch-Service/0.1 OpenAI-Compatible-Relay",
        },
        method="POST",
    )


def _json_or_text(raw: bytes) -> Any:
    text = _decode(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _http_error_message(status: int, raw: bytes, config: AIConfig) -> str:
    payload = _json_or_text(raw)
    if _is_cloudflare_1010_payload(raw, payload):
        code = payload.get("error_code", "")
        name = payload.get("error_name", "")
        ray_id = payload.get("ray_id") or payload.get("instance") or ""
        detail = payload.get("detail") or payload.get("title") or ""
        message = (
            f"HTTP {status}: Cloudflare 拦截了请求"
            f"{f'（Error {code} {name}）' if code or name else ''}。"
            "这不是 API Key 鉴权失败，而是站点按客户端签名拒绝访问；错误说明也建议不要反复重试。"
            "请优先把接口地址改成 Codex 参考的 http://ctoken.top/v1/，接口类型选择 Responses API；"
            "如果仍失败，需要接口服务商放行当前客户端或提供可用于本地服务的 API 地址。"
        )
        if detail:
            message += f" 原始说明：{detail}"
        if ray_id:
            message += f" Ray ID: {ray_id}"
        return _sanitize(message, config)
    return _sanitize(f"HTTP {status}: {_decode(raw)}", config)


def _is_cloudflare_1010_payload(raw: bytes, payload: Any | None = None) -> bool:
    payload = _json_or_text(raw) if payload is None else payload
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("cloudflare_error") or str(payload.get("error_code", "")) == "1010")


def _text_from_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return part["text"]
    return ""


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _sanitize(message: str, config: AIConfig) -> str:
    clean = message.replace(config.api_key, "***") if config.api_key else message
    return clean[:800]
