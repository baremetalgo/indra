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
