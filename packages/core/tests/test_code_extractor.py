"""Tests for production-grade Codebase Knowledge Graph Extractor and AST Chunker."""

from open_graph_core.code_extractor import CodeExtractor, CodeSymbolKind, CodeRelationKind


def test_python_extraction():
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
    assert "BaseManager" in inherits[0].quote

    # Check chunks
    assert len(result.chunks) > 0
    chunk_names = {c.symbol_name for c in result.chunks}
    assert "UserAuth" in chunk_names or "login" in chunk_names


def test_typescript_extraction():
    extractor = CodeExtractor()
    code = '''
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
'''
    result = extractor.extract_file("src/services/userService.ts", code)
    assert result.language == "typescript"
    names = {e.name for e in result.entities}
    assert "UserProfile" in names
    assert "UserService" in names
    assert "getUser" in names


def test_go_extraction():
    extractor = CodeExtractor()
    code = '''
package main

import "fmt"

type Server struct {
    Port int
}

func (s *Server) Start() error {
    fmt.Println("Starting")
    return nil
}
'''
    result = extractor.extract_file("pkg/server/server.go", code)
    assert result.language == "go"
    names = {e.name for e in result.entities}
    assert "Server" in names
    assert "Start" in names


def test_rust_extraction():
    extractor = CodeExtractor()
    code = '''
use std::sync::Arc;

pub struct Config {
    pub port: u16,
}

pub fn run_server(config: Config) {
    println!("Running");
}
'''
    result = extractor.extract_file("src/main.rs", code)
    assert result.language == "rust"
    names = {e.name for e in result.entities}
    assert "Config" in names
    assert "run_server" in names


def test_fallback_extraction():
    extractor = CodeExtractor()
    code = '''
def unknown_func():
    pass
'''
    result = extractor.extract_file("unknown_script.xyz", code)
    assert result.language == "generic"
    assert len(result.entities) >= 1
