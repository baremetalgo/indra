"""Thin tree-sitter wrapper.

Deliberately minimal: parse source bytes for a known extension, return
the tree plus a per-language query for "things worth indexing"
(functions, classes, methods, imports). Python is the only language
wired up so far (per the roadmap: "Python first"); adding a language
means adding one entry to ``_LANGUAGES`` with its own queries, not
touching any other module.
"""

from __future__ import annotations

from dataclasses import dataclass

import tree_sitter
import tree_sitter_python


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

_LANGUAGES: dict[str, LanguageSpec] = {
    ".py": _PYTHON,
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
