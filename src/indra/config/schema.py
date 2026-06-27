"""Typed configuration models for Indra.

These dataclasses are the single source of truth for configuration
shape. ``config/loader.py`` is responsible for turning YAML/TOML/env
input into instances of these classes, validating eagerly so the
process fails fast on bad config rather than deep inside the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    backend: str = "mock"  # mock|llama_cpp|ollama|openai_compat|vllm|lmstudio
    model_path: str = ""
    context_size: int = 4096
    max_tokens_per_call: int = 512
    gpu_layers: int = 20
    temperature: float = 0.0
    flash_attn: bool = False
    """Passed to llama-cpp-python's Llama(flash_attn=...). Requires a
    build/GPU that supports it; silently ignored (with a logged
    warning) if the installed llama-cpp-python version doesn't accept
    the kwarg."""


@dataclass(frozen=True)
class MemoryConfig:
    max_tokens: int = 300
    long_term_retention_days: int = 90


@dataclass(frozen=True)
class AgentConfig:
    max_llm_calls_simple: int = 3
    max_llm_calls_medium: int = 8
    max_llm_calls_complex: int = 15
    max_replan_attempts: int = 1
    max_tool_retries: int = 2
    max_steps: int = 40


@dataclass(frozen=True)
class WebSearchConfig:
    provider: str = "searxng"
    base_url: str = "http://localhost:8080"
    api_key_env: str = ""
    max_results: int = 5
    fetch_timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 3600


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    config_path: str = "./telegram.config.json"


@dataclass(frozen=True)
class HardwareOverride:
    gpu_layers: int | None = None
    context_size: int | None = None
    max_tokens_per_call: int | None = None


@dataclass(frozen=True)
class ShellConfig:
    allow_arbitrary: bool = False
    """If True, bypasses the allowlist entirely -- run any command. Off
    by default; the shell tool is the highest-risk tool in the system."""
    allowlist: tuple[str, ...] = (
        "git", "python", "python3", "pip", "pip3",
        "npm", "npx", "node", "yarn", "pnpm",
        "pytest", "go", "cargo", "make",
        "ls", "dir", "cat", "type", "echo", "pwd",
        "where", "which", "find", "findstr", "grep", "tree",
        "java", "mvn", "gradle", "dotnet", "ruby", "php",
        "rustc", "gcc", "g++", "clang", "tsc",
        "black", "ruff", "flake8", "mypy", "eslint", "prettier",
    )
    timeout_seconds: float = 30.0
    max_output_bytes: int = 200_000


@dataclass(frozen=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8420
    base_url: str = ""
    """If set, the CLI connects to this URL instead of spinning up an
    in-process API. This is the recommended mode for llama.cpp: run
    `indra serve` once (model loads a single time), point every CLI
    invocation at it via this field (or the INDRA_API_URL env var,
    which always takes precedence), and avoid reloading the GGUF model
    on every command.
    """


@dataclass(frozen=True)
class IndraConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    hardware_override: HardwareOverride = field(default_factory=HardwareOverride)
    api: ApiConfig = field(default_factory=ApiConfig)
    shell: ShellConfig = field(default_factory=ShellConfig)
    repo_path: str = "."
    db_path: str = "./.indra/indra.db"
    workspaces_root: str = "./.indra/workspaces"
    plugins: tuple[str, ...] = ()
    log_level: str = "INFO"
