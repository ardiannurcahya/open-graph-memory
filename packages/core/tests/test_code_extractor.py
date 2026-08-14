"""Tests for production-grade Codebase Knowledge Graph Extractor and AST Chunker."""

from open_graph_core.code_extractor import CodeExtractor, CodeRelationKind, CodeSymbolKind


def test_python_extraction() -> None:
    extractor = CodeExtractor()
    code = '''
import os
from datetime import datetime

class BaseManager:
    def setup(self):
        pass

class UserAuth(BaseManager):
    """Handles user authentication."""
    def login(self, username: str) -> bool:
        self.setup()
        return True
'''
    result = extractor.extract_file("apps/api/app/auth.py", code)
    assert result.language == "python"
    assert len(result.entities) >= 4  # File, BaseManager, UserAuth, setup, login

    names = {e.name for e in result.entities}
    assert "UserAuth" in names
    assert "login" in names
    assert "BaseManager" in names

    # Check relation
    inherits = [r for r in result.relations if r.kind == CodeRelationKind.INHERITS]
    assert len(inherits) >= 1
    assert inherits[0].quote is not None and "BaseManager" in inherits[0].quote

    # Check chunks
    assert len(result.chunks) > 0
    chunk_names = {c.symbol_name for c in result.chunks}
    assert "UserAuth" in chunk_names or "login" in chunk_names


def test_typescript_extraction() -> None:
    extractor = CodeExtractor()
    code = """
import { useState } from 'react';

export interface UserProfile {
    id: string;
    name: string;
}

export class UserService {
    getUser(id: string): UserProfile {
        return { id, name: "Alice" };
    }
}

export const handleAutoFill = () => {
    const items = [1, 2, 3];
    items.map((x) => x * 2);
};
"""
    result = extractor.extract_file("src/services/userService.ts", code)
    assert result.language == "typescript"
    names = {e.name for e in result.entities}
    assert "UserProfile" in names
    assert "UserService" in names
    assert "getUser" in names
    assert "handleAutoFill" in names
    assert "anonymous" not in names


def test_go_extraction() -> None:
    extractor = CodeExtractor()
    code = """
package main

import "fmt"

type Server struct {
    Port int
}

func (s *Server) Start() error {
    fmt.Println("Starting")
    return nil
}
"""
    result = extractor.extract_file("pkg/server/server.go", code)
    assert result.language == "go"
    names = {e.name for e in result.entities}
    assert "Server" in names
    assert "Start" in names


def test_rust_extraction() -> None:
    extractor = CodeExtractor()
    code = """
use std::sync::Arc;

pub struct Config {
    pub port: u16,
}

pub fn run_server(config: Config) {
    println!("Running");
}
"""
    result = extractor.extract_file("src/main.rs", code)
    assert result.language == "rust"
    names = {e.name for e in result.entities}
    assert "Config" in names
    assert "run_server" in names


def test_fallback_extraction() -> None:
    extractor = CodeExtractor()
    code = """
def unknown_func():
    pass
"""
    result = extractor.extract_file("unknown_script.xyz", code)
    assert result.language == "generic"
    assert len(result.entities) >= 1


def test_typescript_infers_names_from_declaration_context() -> None:
    """Anonymous functions/arrows should inherit a name from their surrounding
    declarator, assignment, object property, or default export, but truly
    unnamed callbacks (e.g. passed straight into a call) must stay untracked."""
    extractor = CodeExtractor()
    code = """
const onClick = () => {
    console.log("clicked");
};

let onSubmit = function () {
    return true;
};

let helper;
helper = () => 42;

const config = {
    onLoad: () => {},
    timeout: 500,
};

export default function () {
    return "anonymous-export";
}

[1, 2, 3].forEach((item) => console.log(item));
"""
    result = extractor.extract_file("src/widgets/handlers.ts", code)
    assert result.language == "typescript"
    symbol_names = {e.name for e in result.entities if e.kind != CodeSymbolKind.FILE}

    # Named via variable_declarator (const/let), assignment, and object property.
    assert "onClick" in symbol_names
    assert "onSubmit" in symbol_names
    assert "helper" in symbol_names
    assert "onLoad" in symbol_names
    # Named via the "export default" fallback.
    assert "default" in symbol_names
    # No fallback placeholder names should ever be emitted.
    assert "anonymous" not in symbol_names
    # The forEach callback has no declaration context to infer a name from,
    # so it must not appear as a tracked symbol.
    assert "item" not in symbol_names


def test_python_lambda_extraction() -> None:
    """Lambdas assigned to a name are tracked; inline/unassigned lambdas are not."""
    extractor = CodeExtractor()
    code = """
formatter = lambda name: name.upper()


def process(items):
    return sorted(items, key=lambda x: x.lower())
"""
    result = extractor.extract_file("app/format.py", code)
    assert result.language == "python"
    names = {e.name for e in result.entities}
    assert "formatter" in names
    assert "process" in names

    formatter_entity = next(e for e in result.entities if e.name == "formatter")
    assert formatter_entity.kind == CodeSymbolKind.FUNCTION

    # The unassigned lambda passed as `key=` has no declaration context, so it
    # must not be captured as an entity distinct from `formatter` and `process`.
    function_like = [
        e for e in result.entities if e.kind in {CodeSymbolKind.FUNCTION, CodeSymbolKind.METHOD}
    ]
    assert {e.name for e in function_like} == {"formatter", "process"}


def test_go_var_func_literal() -> None:
    """A func literal assigned via `var` is named after the variable; an
    immediately-invoked anonymous goroutine is not tracked."""
    extractor = CodeExtractor()
    code = """
package main

import "fmt"

var handler = func() {
    fmt.Println("handled")
}

func main() {
    go func() {
        fmt.Println("goroutine")
    }()
}
"""
    result = extractor.extract_file("cmd/server/main.go", code)
    assert result.language == "go"
    names = {e.name for e in result.entities}
    assert "handler" in names
    assert "main" in names

    function_entities = [e for e in result.entities if e.kind == CodeSymbolKind.FUNCTION]
    assert {e.name for e in function_entities} == {"handler", "main"}


def test_rust_closure_let_binding() -> None:
    """A closure bound with `let` is named after the pattern; a closure passed
    straight into a call (e.g. `.map(...)`) is not tracked as its own entity."""
    extractor = CodeExtractor()
    code = """
fn main() {
    let adder = |x: i32| x + 1;
    let values = vec![1, 2, 3];
    let doubled: Vec<i32> = values.iter().map(|x| x * 2).collect();
}
"""
    result = extractor.extract_file("src/main.rs", code)
    assert result.language == "rust"
    names = {e.name for e in result.entities}
    assert "adder" in names
    assert "main" in names

    function_entities = [e for e in result.entities if e.kind == CodeSymbolKind.FUNCTION]
    assert {e.name for e in function_entities} == {"main", "adder"}


def test_c_typedef_struct_infers_name_from_declarator() -> None:
    """An anonymous struct wrapped in a `typedef` should take its name from
    the typedef's declarator (the aliased type name)."""
    extractor = CodeExtractor()
    code = """
typedef struct {
    int x;
    int y;
} Point;

int add(int a, int b) {
    return a + b;
}
"""
    result = extractor.extract_file("src/geometry.c", code)
    assert result.language == "c"
    names = {e.name for e in result.entities}
    assert "Point" in names
    assert "add" in names

    struct_entities = [e for e in result.entities if e.kind == CodeSymbolKind.STRUCT]
    assert any(e.name == "Point" for e in struct_entities)
