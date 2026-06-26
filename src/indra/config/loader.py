"""Loads :class:`IndraConfig` from YAML plus ``INDRA_*`` env overrides.

Precedence (highest wins): environment variables > YAML file > dataclass
defaults. Validation happens eagerly in :func:`load_config` so a bad
config is caught at startup, not mid-task.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from indra.config.schema import (
    AgentConfig,
    ApiConfig,
    HardwareOverride,
    IndraConfig,
    MemoryConfig,
    ModelConfig,
    ShellConfig,
    TelegramConfig,
    WebSearchConfig,
)


class ConfigError(Exception):
    """Raised on invalid or unreadable configuration."""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Top-level config in {path} must be a mapping")
    return data


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply INDRA_SECTION__FIELD=value overrides, e.g. INDRA_MODEL__GPU_LAYERS=10."""
    for key, value in os.environ.items():
        if not key.startswith("INDRA_"):
            continue
        path = key[len("INDRA_"):].lower().split("__")
        cursor = raw
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):
                raise ConfigError(f"Env override {key} conflicts with config shape")
        cursor[path[-1]] = value
    return raw


def _build_section(cls: type, data: dict[str, Any] | None) -> Any:
    data = data or {}
    valid_fields = {f for f in cls.__dataclass_fields__}
    unknown = set(data) - valid_fields
    if unknown:
        raise ConfigError(f"Unknown fields for {cls.__name__}: {sorted(unknown)}")
    coerced: dict[str, Any] = {}
    for field_name, field_def in cls.__dataclass_fields__.items():
        if field_name not in data:
            continue
        raw_value = data[field_name]
        field_type = field_def.type
        coerced[field_name] = _coerce_scalar(raw_value, field_type)
    return cls(**coerced)


def _coerce_scalar(value: Any, field_type: Any) -> Any:
    """Best-effort coercion: env-var strings into int/float/bool, and
    YAML lists into tuples (every IndraConfig field is a frozen
    dataclass with hashable fields -- a list anywhere breaks that,
    which breaks the provider lru_cache in api/deps.py)."""
    if isinstance(value, list):
        return tuple(value)
    if not isinstance(value, str):
        return value
    type_str = str(field_type)
    if "bool" in type_str:
        return value.lower() in ("1", "true", "yes", "on")
    if "int" in type_str and "float" not in type_str:
        try:
            return int(value)
        except ValueError:
            return value
    if "float" in type_str:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def validate_config(config: IndraConfig) -> None:
    """Fail-fast checks beyond what dataclass typing alone enforces."""
    errors: list[str] = []

    if config.model.context_size < 512:
        errors.append("model.context_size must be >= 512")
    if not (4096 <= config.model.context_size <= 32768):
        errors.append(
            "model.context_size outside the supported local-model range "
            "(4096-32768); the small-model target is 4096-8192"
        )
    if config.agent.max_llm_calls_simple < 1:
        errors.append("agent.max_llm_calls_simple must be >= 1")
    if config.agent.max_llm_calls_complex < config.agent.max_llm_calls_medium:
        errors.append(
            "agent.max_llm_calls_complex must be >= agent.max_llm_calls_medium"
        )
    if config.agent.max_steps < 1:
        errors.append("agent.max_steps must be >= 1")
    if config.model.backend not in (
        "mock", "llama_cpp", "ollama", "openai_compat", "vllm", "lmstudio",
    ):
        errors.append(f"model.backend unknown: {config.model.backend!r}")
    if not (1 <= config.api.port <= 65535):
        errors.append("api.port must be between 1 and 65535")
    if config.shell.timeout_seconds <= 0:
        errors.append("shell.timeout_seconds must be > 0")
    if config.shell.max_output_bytes <= 0:
        errors.append("shell.max_output_bytes must be > 0")

    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))


def load_config(path: str | Path = "indra.config.yaml") -> IndraConfig:
    """Load, override, and validate the full Indra configuration."""
    raw = _read_yaml(Path(path))
    raw = _apply_env_overrides(raw)

    config = IndraConfig(
        model=_build_section(ModelConfig, raw.get("model")),
        memory=_build_section(MemoryConfig, raw.get("memory")),
        agent=_build_section(AgentConfig, raw.get("agent")),
        web_search=_build_section(WebSearchConfig, raw.get("web_search")),
        telegram=_build_section(TelegramConfig, raw.get("telegram")),
        hardware_override=_build_section(
            HardwareOverride, raw.get("hardware_override")
        ),
        api=_build_section(ApiConfig, raw.get("api")),
        shell=_build_section(ShellConfig, raw.get("shell")),
        repo_path=raw.get("repo_path", "."),
        db_path=raw.get("db_path", "./.indra/indra.db"),
        workspaces_root=raw.get("workspaces_root", "./.indra/workspaces"),
        plugins=tuple(raw.get("plugins", ())),
        log_level=raw.get("log_level", "INFO"),
    )
    validate_config(config)
    return config
