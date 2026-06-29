"""Thin tree-sitter wrapper.

Deliberately minimal: parse source bytes for a known extension, return
the tree plus a per-language spec of "things worth indexing"
(functions, classes, methods, interfaces, imports). Adding a language
means adding one ``LanguageSpec`` entry to ``_LANGUAGES``, not touching
any other module. Python, JavaScript, and TypeScript/TSX are wired up;
CommonJS ``require()`` imports are not detected (only ES module
``import`` statements), and arrow functions assigned to a const are
not extracted as named symbols -- both are reasonable v1 scope limits,
not fundamental ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import tree_sitter
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    language: tree_sitter.Language
    symbol_node_types: dict[str, str]  # tree-sitter node type -> our symbol_kind
    import_node_types: tuple[str, ...]


_PYTHON = LanguageSpec(
    name="python",
    language=tree_sitter.Language(tree_sitter_python.language()),
    symbol_node_types={
        "function_definition": "function",
        "class_definition": "class",
    },
    import_node_types=("import_statement", "import_from_statement"),
)

# JS/TS/TSX share the same symbol/import node type names (TS and TSX
# grammars extend the JS one), plus TS adds interfaces and type aliases.
_JS_SYMBOL_TYPES = {
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
}
_TS_SYMBOL_TYPES = {
    **_JS_SYMBOL_TYPES,
    "interface_declaration": "interface",
    "type_alias_declaration": "type_alias",
}
_JS_IMPORT_TYPES = ("import_statement",)

_JAVASCRIPT = LanguageSpec(
    name="javascript",
    language=tree_sitter.Language(tree_sitter_javascript.language()),
    symbol_node_types=_JS_SYMBOL_TYPES,
    import_node_types=_JS_IMPORT_TYPES,
)

_TYPESCRIPT = LanguageSpec(
    name="typescript",
    language=tree_sitter.Language(tree_sitter_typescript.language_typescript()),
    symbol_node_types=_TS_SYMBOL_TYPES,
    import_node_types=_JS_IMPORT_TYPES,
)

_TSX = LanguageSpec(
    name="tsx",
    language=tree_sitter.Language(tree_sitter_typescript.language_tsx()),
    symbol_node_types=_TS_SYMBOL_TYPES,
    import_node_types=_JS_IMPORT_TYPES,
)

_LANGUAGES: dict[str, LanguageSpec] = {
    ".py": _PYTHON,
    ".js": _JAVASCRIPT,
    ".jsx": _JAVASCRIPT,
    ".mjs": _JAVASCRIPT,
    ".cjs": _JAVASCRIPT,
    ".ts": _TYPESCRIPT,
    ".tsx": _TSX,
}


def language_for(path: str) -> LanguageSpec | None:
    for ext, spec in _LANGUAGES.items():
        if path.endswith(ext):
            return spec
    return None


def parse(source: bytes, spec: LanguageSpec) -> tree_sitter.Tree:
    parser = tree_sitter.Parser(spec.language)
    return parser.parse(source)


def node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
