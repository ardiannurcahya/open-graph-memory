"""Production-grade Codebase Knowledge Graph Extractor and AST Chunker.

Extracts symbols (functions, classes, interfaces, structs, modules),
relations (calls, imports, inherits, implements, contains), and structural AST
code chunks across Python, TypeScript, JavaScript, Go, Rust, C, and C++.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    from tree_sitter_languages import get_parser
    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False


class CodeSymbolKind(str, Enum):  # noqa: UP042
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    VARIABLE = "variable"
    IMPORT = "import"
    TYPE_ALIAS = "type_alias"
    MODULE = "module"


class CodeRelationKind(str, Enum):  # noqa: UP042

    CONTAINS = "contains"
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    TYPE_REFERENCES = "type_references"


class CodeEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    file_path: str
    name: str
    kind: CodeSymbolKind
    language: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    signature: str | None = None
    docstring: str | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    target_id: str
    kind: CodeRelationKind
    file_path: str
    line_number: int
    quote: str | None = None


class ASTChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    file_path: str
    symbol_id: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    index: int
    text: str
    token_count: int
    start_line: int
    end_line: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    language: str
    entities: list[CodeEntity]
    relations: list[CodeRelation]
    chunks: list[ASTChunk]


EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
}


def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LANG.get(ext, "generic")


def canonical_symbol_id(language: str, file_path: str, symbol_name: str, kind: str) -> str:
    norm_path = file_path.replace("\\", "/").strip("/")
    raw = f"{language}:{norm_path}:{kind}:{symbol_name}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", symbol_name)[:40]
    return f"code_{language}_{safe_name}_{digest}"


class CodeExtractor:
    """Production-grade Codebase Knowledge Graph Extractor."""

    def __init__(self, default_chunk_size: int = 1500) -> None:
        self.chunk_size = default_chunk_size

    def extract(
        self, code: str, file_path: str, language: str | None = None
    ) -> CodeExtractionResult:
        return self.extract_file(file_path=file_path, content=code)

    def extract_file(self, file_path: str, content: str) -> CodeExtractionResult:

        language = detect_language(file_path)
        if TREE_SITTER_AVAILABLE and language != "generic":
            try:
                return self._extract_with_treesitter(file_path, content, language)
            except Exception:
                pass
        return self._extract_with_fallback(file_path, content, language)

    def _extract_with_treesitter(
        self, file_path: str, content: str, language: str
    ) -> CodeExtractionResult:
        ts_lang_name = "typescript" if language == "typescript" else language
        if ts_lang_name == "cpp":
            ts_lang_name = "cpp"
        parser = get_parser(ts_lang_name)
        code_bytes = content.encode("utf-8")
        tree = parser.parse(code_bytes)

        file_entity_id = canonical_symbol_id(language, file_path, Path(file_path).name, "file")
        file_entity = CodeEntity(
            id=file_entity_id,
            file_path=file_path,
            name=Path(file_path).name,
            kind=CodeSymbolKind.FILE,
            language=language,
            start_line=1,
            end_line=len(content.splitlines()) or 1,
            start_byte=0,
            end_byte=len(code_bytes),
            signature=file_path,
        )

        entities: list[CodeEntity] = [file_entity]
        relations: list[CodeRelation] = []

        def node_text(node: Any) -> str:

            return code_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        def traverse(node: Any, current_parent_id: str) -> None:
            node_type = node.type
            next_parent_id = current_parent_id

            # --- Python ---
            if language == "python":
                if node_type in {"function_definition", "async_function_definition"}:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "anonymous_func"
                    kind = (
                        CodeSymbolKind.METHOD
                        if current_parent_id != file_entity_id
                        else CodeSymbolKind.FUNCTION
                    )
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)

                    # Docstring
                    docstring = None
                    body_node = node.child_by_field_name("body")
                    if body_node and body_node.children:
                        first_stmt = body_node.children[0]
                        if first_stmt.type == "expression_statement" and first_stmt.children:
                            str_node = first_stmt.children[0]
                            if str_node.type == "string":
                                docstring = node_text(str_node).strip("'\" \n\t")

                    params_node = node.child_by_field_name("parameters")
                    sig = f"def {name}{node_text(params_node)}" if params_node else f"def {name}()"

                    entity = CodeEntity(
                        id=sym_id,
                        file_path=file_path,
                        name=name,
                        kind=kind,
                        language=language,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        signature=sig,
                        docstring=docstring,
                        parent_id=current_parent_id,
                    )
                    entities.append(entity)
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id


                elif node_type == "class_definition":
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "AnonymousClass"
                    sym_id = canonical_symbol_id(language, file_path, name, "class")

                    superclasses = []
                    super_node = node.child_by_field_name(
                        "superclasses"
                    ) or node.child_by_field_name("argument_list")

                    if super_node:
                        for child in super_node.children:
                            if child.type in {"identifier", "attribute"}:
                                superclasses.append(node_text(child))


                    entity = CodeEntity(
                        id=sym_id,
                        file_path=file_path,
                        name=name,
                        kind=CodeSymbolKind.CLASS,
                        language=language,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        signature=f"class {name}",
                        parent_id=current_parent_id,
                        metadata={"superclasses": superclasses},
                    )
                    entities.append(entity)
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    for base in superclasses:
                        base_id = canonical_symbol_id(language, file_path, base, "class")
                        relations.append(
                            CodeRelation(
                                id=f"rel_inherits_{sym_id}_{base}",
                                source_id=sym_id,
                                target_id=base_id,
                                kind=CodeRelationKind.INHERITS,
                                file_path=file_path,
                                line_number=node.start_point[0] + 1,
                                quote=f"class {name}({base}):",
                            )
                        )
                    next_parent_id = sym_id

                elif node_type in {"import_statement", "import_from_statement"}:
                    imp_text = node_text(node).strip()
                    imp_id = canonical_symbol_id(
                        language, file_path, f"import_{node.start_byte}", "import"
                    )
                    entities.append(
                        CodeEntity(
                            id=imp_id,
                            file_path=file_path,
                            name=imp_text[:50],
                            kind=CodeSymbolKind.IMPORT,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=imp_text,
                            parent_id=file_entity_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_imports_{file_entity_id}_{imp_id}",
                            source_id=file_entity_id,
                            target_id=imp_id,
                            kind=CodeRelationKind.IMPORTS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            quote=imp_text,
                        )
                    )

                elif node_type == "call":
                    fn_node = node.child_by_field_name("function")
                    if fn_node:
                        fn_name = node_text(fn_node)
                        if fn_name and current_parent_id != file_entity_id:
                            target_sym_id = canonical_symbol_id(
                                language, file_path, fn_name, "function"
                            )
                            relations.append(
                                CodeRelation(
                                    id=f"rel_calls_{current_parent_id}_{node.start_byte}",
                                    source_id=current_parent_id,
                                    target_id=target_sym_id,
                                    kind=CodeRelationKind.CALLS,
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    quote=node_text(node)[:100],
                                )
                            )

            # --- TypeScript / JavaScript ---
            elif language in {"typescript", "javascript"}:
                if node_type in {"function_declaration", "method_definition", "arrow_function"}:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "anonymous"
                    is_method = node_type == "method_definition"
                    kind = CodeSymbolKind.METHOD if is_method else CodeSymbolKind.FUNCTION
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)


                    params = node.child_by_field_name("parameters")
                    sig = f"function {name}{node_text(params)}" if params else f"function {name}()"

                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=sig,
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

                elif node_type in {
                    "class_declaration", "interface_declaration", "type_alias_declaration"
                }:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "AnonymousType"
                    kind = (
                        CodeSymbolKind.INTERFACE if node_type == "interface_declaration"
                        else CodeSymbolKind.TYPE_ALIAS if node_type == "type_alias_declaration"
                        else CodeSymbolKind.CLASS
                    )
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)

                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{kind.value} {name}",
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

                elif node_type == "import_statement":
                    imp_text = node_text(node).strip()
                    imp_id = canonical_symbol_id(
                        language, file_path, f"import_{node.start_byte}", "import"
                    )

                    entities.append(
                        CodeEntity(
                            id=imp_id,
                            file_path=file_path,
                            name=imp_text[:50],
                            kind=CodeSymbolKind.IMPORT,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=imp_text,
                            parent_id=file_entity_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_imports_{file_entity_id}_{imp_id}",
                            source_id=file_entity_id,
                            target_id=imp_id,
                            kind=CodeRelationKind.IMPORTS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            quote=imp_text,
                        )
                    )

                elif node_type == "call_expression":
                    fn_node = node.child_by_field_name("function")
                    if fn_node:
                        fn_name = node_text(fn_node).strip()
                        if fn_name and current_parent_id != file_entity_id:
                            target_sym_id = canonical_symbol_id(
                                language, file_path, fn_name, "function"
                            )
                            relations.append(
                                CodeRelation(
                                    id=f"rel_calls_{current_parent_id}_{node.start_byte}",
                                    source_id=current_parent_id,
                                    target_id=target_sym_id,
                                    kind=CodeRelationKind.CALLS,
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    quote=fn_name[:100],
                                )
                            )

                elif node_type in {"jsx_element", "jsx_self_closing_element"}:
                    open_node = node.child_by_field_name("open_tag") if node_type == "jsx_element" else node
                    if open_node:
                        tag_node = open_node.child_by_field_name("name")
                        if tag_node:
                            tag_name = node_text(tag_node).strip()
                            # If Component name starts with Uppercase (React Custom Component)
                            if tag_name and tag_name[0].isupper() and current_parent_id != file_entity_id:
                                target_sym_id = canonical_symbol_id(
                                    language, file_path, tag_name, "function"
                                )
                                relations.append(
                                    CodeRelation(
                                        id=f"rel_calls_{current_parent_id}_{node.start_byte}",
                                        source_id=current_parent_id,
                                        target_id=target_sym_id,
                                        kind=CodeRelationKind.CALLS,
                                        file_path=file_path,
                                        line_number=node.start_point[0] + 1,
                                        quote=tag_name[:100],
                                    )
                                )
            elif language == "go":
                if node_type in {"function_declaration", "method_declaration"}:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "anonymous"
                    is_method = node_type == "method_declaration"
                    kind = CodeSymbolKind.METHOD if is_method else CodeSymbolKind.FUNCTION
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)


                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=node_text(node).split("{")[0].strip(),
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

                elif node_type == "type_spec":
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "AnonymousType"
                    type_node = node.child_by_field_name("type")
                    is_struct = type_node and type_node.type == "struct_type"
                    is_iface = type_node and type_node.type == "interface_type"
                    kind = (
                        CodeSymbolKind.STRUCT if is_struct
                        else CodeSymbolKind.INTERFACE if is_iface
                        else CodeSymbolKind.TYPE_ALIAS
                    )
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)


                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"type {name}",
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )

                elif node_type == "import_spec":
                    imp_text = node_text(node).strip()
                    imp_id = canonical_symbol_id(
                        language, file_path, f"import_{node.start_byte}", "import"
                    )
                    entities.append(
                        CodeEntity(
                            id=imp_id,
                            file_path=file_path,
                            name=imp_text.strip('"')[:50],
                            kind=CodeSymbolKind.IMPORT,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=imp_text,
                            parent_id=file_entity_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_imports_{file_entity_id}_{imp_id}",
                            source_id=file_entity_id,
                            target_id=imp_id,
                            kind=CodeRelationKind.IMPORTS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            quote=imp_text,
                        )
                    )

                elif node_type == "call_expression":
                    fn_node = node.child_by_field_name("function")
                    if fn_node:
                        fn_name = node_text(fn_node).strip()
                        if fn_name and current_parent_id != file_entity_id:
                            target_sym_id = canonical_symbol_id(
                                language, file_path, fn_name, "function"
                            )
                            relations.append(
                                CodeRelation(
                                    id=f"rel_calls_{current_parent_id}_{node.start_byte}",
                                    source_id=current_parent_id,
                                    target_id=target_sym_id,
                                    kind=CodeRelationKind.CALLS,
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    quote=fn_name[:100],
                                )
                            )

            # --- Rust ---
            elif language == "rust":
                if node_type in {"function_item", "struct_item", "enum_item", "trait_item"}:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "anonymous"
                    kind = (
                        CodeSymbolKind.FUNCTION if node_type == "function_item"
                        else CodeSymbolKind.STRUCT if node_type == "struct_item"
                        else CodeSymbolKind.ENUM if node_type == "enum_item"
                        else CodeSymbolKind.INTERFACE
                    )
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)

                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=node_text(node).split("{")[0].strip(),
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

            # --- C / C++ ---
            elif language in {"c", "cpp"}:
                if node_type == "function_definition":
                    declarator = node.child_by_field_name("declarator")
                    name = node_text(declarator) if declarator else "function"
                    name = name.split("(")[0].strip()
                    sym_id = canonical_symbol_id(language, file_path, name, "function")

                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=CodeSymbolKind.FUNCTION,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=name,
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

                elif node_type in {"struct_specifier", "class_specifier"}:
                    name_node = node.child_by_field_name("name")
                    name = node_text(name_node) if name_node else "anonymous"
                    is_class = node_type == "class_specifier"
                    kind = CodeSymbolKind.CLASS if is_class else CodeSymbolKind.STRUCT
                    sym_id = canonical_symbol_id(language, file_path, name, kind.value)


                    entities.append(
                        CodeEntity(
                            id=sym_id,
                            file_path=file_path,
                            name=name,
                            kind=kind,
                            language=language,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{kind.value} {name}",
                            parent_id=current_parent_id,
                        )
                    )
                    relations.append(
                        CodeRelation(
                            id=f"rel_contains_{current_parent_id}_{sym_id}",
                            source_id=current_parent_id,
                            target_id=sym_id,
                            kind=CodeRelationKind.CONTAINS,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        )
                    )
                    next_parent_id = sym_id

            for child in node.children:
                traverse(child, next_parent_id)

        traverse(tree.root_node, file_entity_id)


        chunks = self._generate_ast_chunks(file_path, content, entities)

        return CodeExtractionResult(
            file_path=file_path,
            language=language,
            entities=entities,
            relations=relations,
            chunks=chunks,
        )

    def _extract_with_fallback(
        self, file_path: str, content: str, language: str
    ) -> CodeExtractionResult:
        file_entity_id = canonical_symbol_id(language, file_path, Path(file_path).name, "file")
        lines = content.splitlines()
        file_entity = CodeEntity(
            id=file_entity_id,
            file_path=file_path,
            name=Path(file_path).name,
            kind=CodeSymbolKind.FILE,
            language=language,
            start_line=1,
            end_line=len(lines) or 1,
            start_byte=0,
            end_byte=len(content.encode("utf-8")),
            signature=file_path,
        )

        entities: list[CodeEntity] = [file_entity]
        relations: list[CodeRelation] = []

        func_regex = re.compile(
            r"^\s*(?:async\s+)?(?:def|function|fn|func|class|struct|interface|type)\s+([A-Za-z0-9_]+)",
            re.MULTILINE,
        )

        for i, line in enumerate(lines, 1):
            match = func_regex.search(line)
            if match:
                name = match.group(1)
                is_fn = "def" in line or "function" in line or "fn" in line
                kind = CodeSymbolKind.FUNCTION if is_fn else CodeSymbolKind.CLASS
                sym_id = canonical_symbol_id(language, file_path, name, kind.value)

                entities.append(
                    CodeEntity(
                        id=sym_id,
                        file_path=file_path,
                        name=name,
                        kind=kind,
                        language=language,
                        start_line=i,
                        end_line=min(i + 20, len(lines)),
                        start_byte=0,
                        end_byte=len(content.encode("utf-8")),
                        signature=line.strip(),
                        parent_id=file_entity_id,
                    )
                )
                relations.append(
                    CodeRelation(
                        id=f"rel_contains_{file_entity_id}_{sym_id}",
                        source_id=file_entity_id,
                        target_id=sym_id,
                        kind=CodeRelationKind.CONTAINS,
                        file_path=file_path,
                        line_number=i,
                    )
                )

        chunks = self._generate_ast_chunks(file_path, content, entities)
        return CodeExtractionResult(
            file_path=file_path,
            language=language,
            entities=entities,
            relations=relations,
            chunks=chunks,
        )

    def _generate_ast_chunks(
        self, file_path: str, content: str, entities: Sequence[CodeEntity]
    ) -> list[ASTChunk]:
        lines = content.splitlines()
        chunks: list[ASTChunk] = []

        symbol_entities = [e for e in entities if e.kind != CodeSymbolKind.FILE]

        if not symbol_entities:
            chunks.append(
                ASTChunk(
                    id=f"chunk_{file_path}_0",
                    file_path=file_path,
                    symbol_id=None,
                    symbol_name=Path(file_path).name,
                    symbol_kind="file",
                    index=0,
                    text=content[: self.chunk_size],
                    token_count=len(content[: self.chunk_size].split()),
                    start_line=1,
                    end_line=len(lines) or 1,
                )
            )
            return chunks

        for idx, entity in enumerate(symbol_entities):
            start_l = max(1, entity.start_line)
            end_l = min(len(lines), entity.end_line)
            chunk_lines = lines[start_l - 1 : end_l]
            chunk_text = "\n".join(chunk_lines)

            chunks.append(
                ASTChunk(
                    id=f"chunk_{file_path}_{entity.name}_{idx}",
                    file_path=file_path,
                    symbol_id=entity.id,
                    symbol_name=entity.name,
                    symbol_kind=entity.kind.value,
                    index=idx,
                    text=chunk_text,
                    token_count=len(chunk_text.split()),
                    start_line=start_l,
                    end_line=end_l,
                    metadata={
                        "signature": entity.signature,
                        "docstring": entity.docstring,
                        "parent_id": entity.parent_id,
                    },
                )
            )

        return chunks
