"""A simple, registry-based plugin system — no DI container.

A plugin is a normal Python module that, on import, calls
``REGISTRY.register(...)``. Discovery is explicit: module paths listed
under ``plugins:`` in ``indra.config.yaml`` are imported by
:func:`load_plugins`, which triggers their registration calls. No
filesystem scanning, so startup stays deterministic.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Literal

PluginKind = Literal["tool", "memory_provider", "retrieval_provider", "model_provider", "workflow_stage"]


@dataclass(frozen=True)
class PluginMeta:
    name: str
    kind: PluginKind


class PluginRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., object]] = {}
        self._meta: dict[str, PluginMeta] = {}

    def register(self, meta: PluginMeta, factory: Callable[..., object]) -> None:
        self._factories[meta.name] = factory
        self._meta[meta.name] = meta

    def create(self, name: str, **kwargs: object) -> object:
        return self._factories[name](**kwargs)

    def list_by_kind(self, kind: PluginKind) -> list[PluginMeta]:
        return [m for m in self._meta.values() if m.kind == kind]


REGISTRY = PluginRegistry()


def load_plugins(module_paths: tuple[str, ...]) -> None:
    """Import each configured plugin module, triggering its registration."""
    for path in module_paths:
        importlib.import_module(path)
