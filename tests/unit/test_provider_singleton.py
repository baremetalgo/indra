from __future__ import annotations

from indra.api.deps import _build_provider_singleton
from indra.config.schema import IndraConfig, ModelConfig
from indra.providers.mock_provider import MockProvider


def test_same_config_returns_the_same_provider_instance() -> None:
    config = IndraConfig(model=ModelConfig(backend="mock"))
    a = _build_provider_singleton(config)
    b = _build_provider_singleton(config)
    assert a is b


def test_equal_but_distinct_config_objects_share_the_cached_provider() -> None:
    """IndraConfig is a frozen dataclass; equal configs must hit the same
    cache entry even if they're different Python objects, since the
    whole point is one model load per distinct configuration."""
    config_a = IndraConfig(model=ModelConfig(backend="mock", gpu_layers=10))
    config_b = IndraConfig(model=ModelConfig(backend="mock", gpu_layers=10))
    assert config_a == config_b
    assert _build_provider_singleton(config_a) is _build_provider_singleton(config_b)


def test_different_config_gets_a_different_provider() -> None:
    config_a = IndraConfig(model=ModelConfig(backend="mock", gpu_layers=10))
    config_b = IndraConfig(model=ModelConfig(backend="mock", gpu_layers=20))
    assert _build_provider_singleton(config_a) is not _build_provider_singleton(config_b)


def test_mock_backend_builds_a_mock_provider() -> None:
    config = IndraConfig(model=ModelConfig(backend="mock", gpu_layers=999))
    provider = _build_provider_singleton(config)
    assert isinstance(provider, MockProvider)
