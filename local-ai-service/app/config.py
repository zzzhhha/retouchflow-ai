from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    tomllib = None


@dataclass
class AIConfig:
    provider: str = "mock"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    wire_api: str = "responses"
    enabled: bool = False

    @property
    def configured(self) -> bool:
        return self.enabled and self.provider != "mock" and bool(self.api_key) and bool(self.model)

    @property
    def masked_api_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

    @property
    def public_base_url(self) -> str:
        if self.base_url and _looks_like_secret(self.base_url):
            return ""
        return self.base_url

    @property
    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if _looks_like_url(self.api_key) and _looks_like_secret(self.base_url):
            warnings.append("API Key 和接口地址可能填反了，系统已在运行时按正确位置读取。")
        if self.base_url and _looks_like_secret(self.base_url):
            warnings.append("接口地址看起来像密钥，请重新填写为 https://.../v1 这类地址。")
        if _is_ctoken_base_without_v1(self.base_url):
            warnings.append("当前 ctoken.top 接口地址缺少 /v1，建议按 Codex 参考填写为 http://ctoken.top/v1/。")
        return warnings


def config_dir() -> Path:
    env_dir = os.getenv("AI_RETOUCH_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[1] / "config"


def config_path() -> Path:
    return config_dir() / "settings.json"


def load_ai_config() -> AIConfig:
    data: dict[str, Any] = {}
    path = config_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    provider = os.getenv("AI_RETOUCH_PROVIDER", data.get("provider", "mock"))
    api_key = os.getenv("AI_RETOUCH_API_KEY", data.get("api_key", ""))
    base_url = os.getenv("AI_RETOUCH_BASE_URL", data.get("base_url", ""))
    model = os.getenv("AI_RETOUCH_MODEL", data.get("model", ""))
    wire_api = os.getenv("AI_RETOUCH_WIRE_API", data.get("wire_api", "responses"))
    enabled_raw = os.getenv("AI_RETOUCH_ENABLED", data.get("enabled", False))
    enabled = str(enabled_raw).lower() in {"1", "true", "yes", "on"} if isinstance(enabled_raw, str) else bool(enabled_raw)

    api_key = str(api_key or "")
    base_url = str(base_url or "")
    if _looks_like_url(api_key) and _looks_like_secret(base_url):
        api_key, base_url = base_url, api_key
    base_url = normalize_base_url(base_url)

    return AIConfig(
        provider=str(provider or "mock"),
        api_key=api_key,
        base_url=base_url,
        model=str(model or ""),
        wire_api=normalize_wire_api(str(wire_api or "")),
        enabled=enabled,
    )


def save_ai_config(config: AIConfig) -> Path:
    if _looks_like_url(config.api_key) and _looks_like_secret(config.base_url):
        config = AIConfig(
            provider=config.provider,
            api_key=config.base_url,
            base_url=config.api_key,
            model=config.model,
            wire_api=config.wire_api,
            enabled=config.enabled,
        )
    config.base_url = normalize_base_url(config.base_url)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def public_ai_config() -> dict[str, Any]:
    config = load_ai_config()
    return {
        "provider": config.provider,
        "base_url": config.public_base_url,
        "model": config.model,
        "wire_api": config.wire_api,
        "enabled": config.enabled,
        "configured": config.configured,
        "masked_api_key": config.masked_api_key,
        "warnings": config.warnings,
    }


def normalize_wire_api(value: str) -> str:
    clean = value.strip().lower().replace("-", "_")
    if clean in {"relay", "openai_relay", "relay_auto", "auto_relay", "openai_compatible_relay"}:
        return "openai_relay"
    if clean in {"chat", "chat_completion", "chat_completions"}:
        return "chat_completions"
    if clean in {"completion", "completions", "completion_model", "completion_models", "model_completions", "text_completions"}:
        return "completions"
    if clean in {"legacy_completion", "legacy_completions", "engine_completions", "engines_completions"}:
        return "legacy_completions"
    if clean in {"response", "responses"}:
        return "responses"
    return "responses"


def normalize_base_url(value: str) -> str:
    clean = str(value or "").strip()
    if _is_ctoken_base_without_v1(clean):
        return clean.rstrip("/") + "/v1"
    return clean


def codex_reference_config() -> dict[str, Any]:
    path = Path.home() / ".codex" / "config.toml"
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text) if tomllib else _parse_codex_config_toml(text)
    except OSError:
        return {}
    except Exception:
        return {}

    provider_key = str(data.get("model_provider") or "")
    providers = data.get("model_providers") or {}
    provider = providers.get(provider_key) if isinstance(providers, dict) else {}
    if not isinstance(provider, dict):
        provider = {}

    return {
        "provider": provider_key or provider.get("name", ""),
        "base_url": provider.get("base_url", ""),
        "wire_api": normalize_wire_api(str(provider.get("wire_api", "responses"))),
        "model": data.get("model", ""),
        "review_model": data.get("review_model", ""),
        "requires_openai_auth": bool(provider.get("requires_openai_auth", False)),
    }


def _looks_like_url(value: str) -> bool:
    clean = value.strip().lower()
    return clean.startswith("http://") or clean.startswith("https://")


def _looks_like_secret(value: str) -> bool:
    clean = value.strip()
    if clean.startswith(("sk-", "sk_", "sk-proj-", "sess-", "ak-")):
        return True
    return len(clean) >= 32 and " " not in clean and not _looks_like_url(clean)


def _is_ctoken_base_without_v1(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return host == "ctoken.top" and path in {"", "/"}


def _parse_codex_config_toml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {"model_providers": {}}
    current: dict[str, Any] = data
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith("model_providers."):
                name = section.split(".", 1)[1].strip().strip('"').strip("'")
                current = data["model_providers"].setdefault(name, {})
            else:
                current = data.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = _parse_toml_scalar(value.strip())
    return data


def _parse_toml_scalar(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value
