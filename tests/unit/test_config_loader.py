from __future__ import annotations

import pytest

from indra.config.loader import ConfigError, load_config


def test_default_config_loads_with_no_file(tmp_path) -> None:
    config = load_config(tmp_path / "missing.yaml")
    assert config.model.backend == "mock"
    assert config.agent.max_steps == 40


def test_yaml_overrides_defaults(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("model:\n  backend: llama_cpp\n  gpu_layers: 12\n")
    config = load_config(path)
    assert config.model.backend == "llama_cpp"
    assert config.model.gpu_layers == 12


def test_env_override_takes_precedence(tmp_path, monkeypatch) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("model:\n  gpu_layers: 5\n")
    monkeypatch.setenv("INDRA_MODEL__GPU_LAYERS", "99")
    config = load_config(path)
    assert config.model.gpu_layers == 99


def test_invalid_backend_rejected(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("model:\n  backend: not_a_backend\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_unknown_field_rejected(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("model:\n  totally_made_up_field: 1\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_context_size_too_small_rejected(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("model:\n  context_size: 256\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_api_config_defaults_to_in_process_mode(tmp_path) -> None:
    config = load_config(tmp_path / "missing.yaml")
    assert config.api.base_url == ""
    assert config.api.host == "127.0.0.1"
    assert config.api.port == 8420


def test_api_config_base_url_overrides_in_process_default(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("api:\n  base_url: \"http://127.0.0.1:9999\"\n")
    config = load_config(path)
    assert config.api.base_url == "http://127.0.0.1:9999"


def test_invalid_port_rejected(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("api:\n  port: 999999\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_shell_config_defaults_have_no_arbitrary_execution(tmp_path) -> None:
    config = load_config(tmp_path / "missing.yaml")
    assert config.shell.allow_arbitrary is False
    assert "git" in config.shell.allowlist
    assert "rm" not in config.shell.allowlist


def test_yaml_list_allowlist_becomes_a_hashable_tuple(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("shell:\n  allowlist: [git, python, custom_tool]\n")
    config = load_config(path)
    assert config.shell.allowlist == ("git", "python", "custom_tool")
    # The whole point: IndraConfig must stay hashable for the provider
    # lru_cache in api/deps.py to work at all.
    hash(config)


def test_invalid_shell_timeout_rejected(tmp_path) -> None:
    path = tmp_path / "indra.config.yaml"
    path.write_text("shell:\n  timeout_seconds: 0\n")
    with pytest.raises(ConfigError):
        load_config(path)
