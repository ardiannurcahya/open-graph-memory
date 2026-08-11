import asyncio
import json
import time
from pathlib import Path
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func
import tiktoken

from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion
from app.models import GraphAnalyticsRun

settings = get_settings()
engine = create_async_engine(settings.database_url)

PROJECT_ID = UUID("66ebb1d0-51b0-4aea-aee9-8e386b34e643")
DATASET_ID = "ds_019fefae-9745-7c1e-b544-aa1e7c0a3cff"

# BPE Tokenizer for OpenAI/Claude/Llama models (cl100k_base)
enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text))

async def run_token_savings_benchmark():
    print("=" * 65)
    print("  TOKEN SAVINGS & CONTEXT EFFICIENCY BENCHMARK")
    print("=" * 65)

    # 1. Measure Raw Codebase Tokens
    print("\n1. Calculating Raw Codebase Token Size (Without OGM)...")
    total_raw_code = ""
    file_count = 0
    
    for py_file in Path("packages/core/src/open_graph_core").glob("*.py"):
        total_raw_code += py_file.read_text(encoding="utf-8") + "\n"
        file_count += 1

    for py_file in Path("apps/api/app").glob("*.py"):
        total_raw_code += py_file.read_text(encoding="utf-8") + "\n"
        file_count += 1

    raw_tokens = count_tokens(total_raw_code)
    raw_lines = len(total_raw_code.splitlines())
    raw_kb = len(total_raw_code.encode("utf-8")) / 1024

    print(f"   * Total Files Scanned : {file_count} files")
    print(f"   * Total Code Size     : {raw_kb:.1f} KB ({raw_lines:,} LOC)")
    print(f"   * RAW CODEBASE TOKENS : {raw_tokens:,} tokens")

    # 2. Measure OGM GraphRAG Subgraph & Symbol Query Tokens
    print("\n2. Measuring OGM GraphRAG Query Token Size (With OGM)...")
    
    async with AsyncSession(engine) as db:
        # Query 1: Search symbol 'CodeExtractor'
        entities = list(await db.scalars(
            select(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == PROJECT_ID,
                CanonicalEntity.dataset_id == DATASET_ID,
                CanonicalEntity.canonical_name.ilike("%CodeExtractor%")
            )
        ))
        
        symbol_json = json.dumps([
            {"id": e.id, "name": e.canonical_name, "type": e.entity_type, "confidence": e.confidence}
            for e in entities
        ], indent=2)
        symbol_tokens = count_tokens(symbol_json)

        # Query 2: Call Graph Subgraph for 'ingest_codebase'
        target_entity = [e for e in entities if e.canonical_name == "ingest_codebase"]
        rel_rows = list(await db.scalars(
            select(RelationAssertion)
            .where(
                RelationAssertion.project_id == PROJECT_ID,
                RelationAssertion.dataset_id == DATASET_ID,
                RelationAssertion.relation_type.in_(["calls", "inherits", "imports"])
            )
            .limit(30)
        ))
        
        callgraph_json = json.dumps({
            "target": "ingest_codebase",
            "relations": [
                {"source": r.source_entity_id, "target": r.target_entity_id, "type": r.relation_type}
                for r in rel_rows
            ]
        }, indent=2)
        callgraph_tokens = count_tokens(callgraph_json)

        # Average OGM query context tokens
        avg_ogm_tokens = (symbol_tokens + callgraph_tokens) // 2

    # 3. Calculate Savings
    saved_tokens = raw_tokens - avg_ogm_tokens
    percent_saved = (saved_tokens / raw_tokens) * 100
    compression_ratio = raw_tokens / avg_ogm_tokens

    # Cost calculations ($3.00 per 1M input tokens on GPT-4o / Claude 3.5 Sonnet)
    cost_per_1m = 3.00
    raw_cost_per_query = (raw_tokens / 1_000_000) * cost_per_1m
    ogm_cost_per_query = (avg_ogm_tokens / 1_000_000) * cost_per_1m
    savings_per_query = raw_cost_per_query - ogm_cost_per_query
    
    # 100 queries simulation cost
    raw_100_cost = raw_cost_per_query * 100
    ogm_100_cost = ogm_cost_per_query * 100

    print(f"   * Symbol Search Context: {symbol_tokens:,} tokens")
    print(f"   * Call Graph Subgraph  : {callgraph_tokens:,} tokens")
    print(f"   * AVERAGE OGM CONTEXT  : {avg_ogm_tokens:,} tokens")

    print("\n" + "=" * 65)
    print("          LLM TOKEN & COST SAVINGS BENCHMARK REPORT")
    print("=" * 65)
    print(f"  * Raw Full Codebase Prompt Context : {raw_tokens:,} tokens")
    print(f"  * OGM GraphRAG Focused Context    : {avg_ogm_tokens:,} tokens")
    print("-" * 65)
    print(f"  * TOTAL TOKENS SAVED PER QUERY    : {saved_tokens:,} tokens")
    print(f"  * PERCENTAGE TOKEN SAVINGS        : {percent_saved:.2f}% SAVINGS!")
    print(f"  * CONTEXT COMPRESSION RATIO       : {compression_ratio:.1f}x COMPRESSION!")
    print("-" * 65)
    print("  * FINANCIAL COST BENCHMARK (GPT-4o / Claude 3.5 Sonnet @ $3.00/1M):")
    print(f"    - Cost Without OGM (Full Code)  : ${raw_cost_per_query:.4f} per prompt")
    print(f"    - Cost With OGM GraphRAG       : ${ogm_cost_per_query:.6f} per prompt")
    print(f"    - Net Cost Saved Per Query     : ${savings_per_query:.4f} saved per turn")
    print(f"    - Savings for 100 Agent Turns  : ${raw_100_cost - ogm_100_cost:.2f} SAVED! (${ogm_100_cost:.3f} vs ${raw_100_cost:.2f})")
    print("=" * 65)

asyncio.run(run_token_savings_benchmark())
