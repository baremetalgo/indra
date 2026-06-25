from __future__ import annotations

from indra.plugins.registry import PluginMeta, PluginRegistry


def test_register_and_create() -> None:
    registry = PluginRegistry()
    registry.register(PluginMeta(name="echo_tool", kind="tool"), lambda: "created")
    assert registry.create("echo_tool") == "created"


def test_list_by_kind_filters_correctly() -> None:
    registry = PluginRegistry()
    registry.register(PluginMeta(name="a", kind="tool"), lambda: None)
    registry.register(PluginMeta(name="b", kind="workflow_stage"), lambda: None)
    tools = registry.list_by_kind("tool")
    assert [m.name for m in tools] == ["a"]
