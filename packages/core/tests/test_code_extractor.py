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


def test_python_lambda_assigned_to_variable_infers_name() -> None:
    extractor = CodeExtractor()
    code = """
handler = lambda x: x + 1
"""
    result = extractor.extract_file("src/handlers.py", code)
    names = {e.name for e in result.entities}
    assert "handler" in names
    handler_entity = next(e for e in result.entities if e.name == "handler")
    assert handler_entity.kind == CodeSymbolKind.FUNCTION


def test_python_anonymous_lambda_argument_not_extracted() -> None:
    extractor = CodeExtractor()
    code = """
items = [3, 1, 2]
result = sorted(items, key=lambda x: x)
"""
    result = extractor.extract_file("src/sort_items.py", code)
    function_names = {e.name for e in result.entities if e.kind == CodeSymbolKind.FUNCTION}
    assert function_names == set()


def test_typescript_infers_name_from_object_property_and_class_field() -> None:
    extractor = CodeExtractor()
    code = """
const handlers = {
    onClick: () => {
        console.log("clicked");
    },
};

class Widget {
    onHover = () => {
        console.log("hover");
    };
}
"""
    result = extractor.extract_file("src/widget.ts", code)
    names = {e.name for e in result.entities}
    assert "onClick" in names
    assert "onHover" in names
    assert "anonymous" not in names


def test_typescript_function_expression_assigned_to_variable() -> None:
    extractor = CodeExtractor()
    code = """
const helper = function() {
    return 1;
};
"""
    result = extractor.extract_file("src/helper.ts", code)
    names = {e.name for e in result.entities}
    assert "helper" in names


def test_typescript_export_default_anonymous_function_named_default() -> None:
    extractor = CodeExtractor()
    code = """
export default function() {
    return 42;
}
"""
    result = extractor.extract_file("src/main.ts", code)
    names = {e.name for e in result.entities}
    assert "default" in names


def test_typescript_export_default_anonymous_class_named_default() -> None:
    extractor = CodeExtractor()
    code = """
export default class {
    method() {
        return true;
    }
}
"""
    result = extractor.extract_file("src/component.ts", code)
    names = {e.name for e in result.entities}
    assert "default" in names


def test_go_anonymous_func_literal_not_extracted() -> None:
    extractor = CodeExtractor()
    code = """
package main

func main() {
    go func() {
        println("hello")
    }()
}
"""
    result = extractor.extract_file("main.go", code)
    function_names = [e.name for e in result.entities if e.kind == CodeSymbolKind.FUNCTION]
    assert function_names == ["main"]


def test_rust_closure_let_assignment_named() -> None:
    extractor = CodeExtractor()
    code = """
fn compute() {
    let doubler = |x: i32| x * 2;
    doubler(4);
}
"""
    result = extractor.extract_file("src/lib.rs", code)
    names = {e.name for e in result.entities}
    assert "doubler" in names
    assert "compute" in names


def test_rust_anonymous_closure_argument_not_extracted() -> None:
    extractor = CodeExtractor()
    code = """
fn run(values: Vec<i32>) -> Vec<i32> {
    values.iter().map(|x| x * 2).collect()
}
"""
    result = extractor.extract_file("src/lib.rs", code)
    function_names = [e.name for e in result.entities if e.kind == CodeSymbolKind.FUNCTION]
    assert function_names == ["run"]


def test_c_extraction() -> None:
    extractor = CodeExtractor()
    code = """
struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}
"""
    result = extractor.extract_file("src/math.c", code)
    assert result.language == "c"
    names = {e.name for e in result.entities}
    assert "Point" in names
    assert "add" in names


def test_c_typedef_anonymous_struct_uses_typedef_name() -> None:
    extractor = CodeExtractor()
    code = """
typedef struct {
    int x;
    int y;
} Point;
"""
    result = extractor.extract_file("src/point.c", code)
    struct_entities = [e for e in result.entities if e.kind == CodeSymbolKind.STRUCT]
    assert any(e.name == "Point" for e in struct_entities)


def test_c_anonymous_inline_struct_not_extracted() -> None:
    extractor = CodeExtractor()
    code = """
struct {
    int x;
} instance;
"""
    result = extractor.extract_file("src/anon.c", code)
    struct_names = {e.name for e in result.entities if e.kind == CodeSymbolKind.STRUCT}
    assert struct_names == set()
