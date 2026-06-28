from __future__ import annotations

from indra.coding.ast_inspect import language_for, node_text, parse


def test_language_for_python_extension() -> None:
    spec = language_for("foo/bar.py")
    assert spec is not None
    assert spec.name == "python"


def test_language_for_unknown_extension_returns_none() -> None:
    assert language_for("foo/bar.xyz") is None


def test_parse_extracts_function_definition_node() -> None:
    spec = language_for("a.py")
    source = b"def foo(x):\n    return x + 1\n"
    tree = parse(source, spec)
    root = tree.root_node
    assert root.type == "module"
    func_nodes = [c for c in root.children if c.type == "function_definition"]
    assert len(func_nodes) == 1
    name_node = func_nodes[0].child_by_field_name("name")
    assert node_text(name_node, source) == "foo"


def test_parse_extracts_class_and_method() -> None:
    spec = language_for("a.py")
    source = b"class Foo:\n    def bar(self):\n        pass\n"
    tree = parse(source, spec)
    class_nodes = [c for c in tree.root_node.children if c.type == "class_definition"]
    assert len(class_nodes) == 1
