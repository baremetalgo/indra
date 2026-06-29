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


def test_language_for_javascript_extensions() -> None:
    for ext in (".js", ".jsx", ".mjs", ".cjs"):
        spec = language_for(f"foo/bar{ext}")
        assert spec is not None
        assert spec.name == "javascript"


def test_language_for_typescript_extension() -> None:
    spec = language_for("foo/bar.ts")
    assert spec is not None
    assert spec.name == "typescript"


def test_language_for_tsx_extension() -> None:
    spec = language_for("foo/bar.tsx")
    assert spec is not None
    assert spec.name == "tsx"


def test_javascript_extracts_function_class_and_method() -> None:
    spec = language_for("a.js")
    source = b"function foo() {}\nclass Bar {\n  method() {}\n}\n"
    tree = parse(source, spec)

    found = {}

    def walk(node):
        kind = spec.symbol_node_types.get(node.type)
        if kind:
            name_node = node.child_by_field_name("name")
            found[node_text(name_node, source)] = kind
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    assert found == {"foo": "function", "Bar": "class", "method": "method"}


def test_typescript_extracts_interface_and_type_alias() -> None:
    spec = language_for("a.ts")
    source = b"interface Foo { x: number; }\ntype Bar = string;\n"
    tree = parse(source, spec)

    found = {}

    def walk(node):
        kind = spec.symbol_node_types.get(node.type)
        if kind:
            name_node = node.child_by_field_name("name")
            found[node_text(name_node, source)] = kind
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    assert found == {"Foo": "interface", "Bar": "type_alias"}


def test_javascript_import_statement_is_recognized() -> None:
    spec = language_for("a.js")
    source = b'import { foo } from "./bar";\n'
    tree = parse(source, spec)
    import_nodes = [c for c in tree.root_node.children if c.type in spec.import_node_types]
    assert len(import_nodes) == 1
