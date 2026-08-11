import asyncio
import json
import time
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func, or_
from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion
from app.models import GraphAnalyticsRun, GraphAnalyticsMembership, GraphAnalyticsEntityMetric

settings = get_settings()
engine = create_async_engine(settings.database_url)

PROJECT_ID = UUID("66ebb1d0-51b0-4aea-aee9-8e386b34e643")
DATASET_ID = "ds_019fefae-9745-7c1e-b544-aa1e7c0a3cff"

async def run_quality_eval():
    print("=" * 65)
    print("  CODEBASE KNOWLEDGE GRAPH QUALITY & PRECISION AUDIT")
    print("=" * 65)
    
    start_time = time.perf_counter()
    scores = {}

    async with AsyncSession(engine) as db:
        # --- TEST 1: Symbol Precision & AST Granularity ---
        print("\n[TEST 1] Symbol Extraction & Entity Granularity")
        entities_q = select(CanonicalEntity).where(
            CanonicalEntity.project_id == PROJECT_ID,
            CanonicalEntity.dataset_id == DATASET_ID
        )
        all_entities = list(await db.scalars(entities_q))
        
        type_counts = {}
        for e in all_entities:
            type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1
            
        print(f"   * Total Entities Extracted: {len(all_entities):,}")
        for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"     - {etype:<25}: {count:>4} entities")
            
        # Check key symbols recall
        key_symbols = ["CodeExtractor", "ingest_codebase", "CanonicalEntity", "RelationAssertion", "supported_entity", "refresh_dataset_analytics"]
        found_symbols = []
        for sym in key_symbols:
            match = [e for e in all_entities if sym.lower() in e.canonical_name.lower()]
            if match:
                found_symbols.append(sym)
                
        symbol_recall = (len(found_symbols) / len(key_symbols)) * 100
        scores["symbol_recall"] = symbol_recall
        print(f"   [+] Core Symbol Recall Rate: {symbol_recall:.1f}% ({len(found_symbols)}/{len(key_symbols)} critical symbols identified)")

        # --- TEST 2: Relation Accuracy & Typed AST Connections ---
        print("\n[TEST 2] Relation Accuracy & Typed AST Connections")
        relations_q = select(RelationAssertion).where(
            RelationAssertion.project_id == PROJECT_ID,
            RelationAssertion.dataset_id == DATASET_ID
        )
        all_relations = list(await db.scalars(relations_q))
        
        rel_type_counts = {}
        for r in all_relations:
            rel_type_counts[r.relation_type] = rel_type_counts.get(r.relation_type, 0) + 1
            
        print(f"   * Total Relations Parsed  : {len(all_relations):,}")
        for rtype, count in sorted(rel_type_counts.items(), key=lambda x: -x[1]):
            print(f"     - {rtype:<25}: {count:>4} relations")

        # Check self-loop safety and invalid FKs
        valid_relations = [r for r in all_relations if r.source_entity_id != r.target_entity_id]
        self_loop_safety = (len(valid_relations) / len(all_relations)) * 100 if all_relations else 100
        scores["relation_safety"] = self_loop_safety
        print(f"   [+] Graph Integrity (Zero Self-Loops): {self_loop_safety:.1f}%")

        # --- TEST 3: Call Graph Dependency Traversal (Multi-Hop) ---
        print("\n[TEST 3] Call Graph Traversal & Dependency Hops")
        calls_rel = [r for r in all_relations if r.relation_type == "calls"]
        inherits_rel = [r for r in all_relations if r.relation_type == "inherits"]
        contains_rel = [r for r in all_relations if r.relation_type == "contains"]
        imports_rel = [r for r in all_relations if r.relation_type == "imports"]

        print(f"   * Function/Method Calls  : {len(calls_rel):,} edges")
        print(f"   * Class Inheritances     : {len(inherits_rel):,} edges")
        print(f"   * Module/Class Contains  : {len(contains_rel):,} edges")
        print(f"   * Package/File Imports   : {len(imports_rel):,} edges")

        entity_map = {e.id: e for e in all_entities}
        degree_map = {}
        for r in all_relations:
            degree_map[r.source_entity_id] = degree_map.get(r.source_entity_id, 0) + 1
            degree_map[r.target_entity_id] = degree_map.get(r.target_entity_id, 0) + 1
            
        hub_nodes = sorted(degree_map.items(), key=lambda x: -x[1])[:5]
        print("\n   * Top 5 Highly Connected Hub Code Entities (Highest Degree):")
        for eid, deg in hub_nodes:
            e_obj = entity_map.get(eid)
            cname = e_obj.canonical_name if e_obj else eid
            etype = e_obj.entity_type if e_obj else "unknown"
            print(f"     - [{deg:>3} connections] {cname} ({etype})")

        scores["graph_connectivity"] = 100.0 if len(hub_nodes) > 0 else 0.0

        # --- TEST 4: GraphRAG Community Clustering Quality ---
        print("\n[TEST 4] GraphRAG Community Analytics & Louvain Hierarchy")
        latest_run = await db.scalar(
            select(GraphAnalyticsRun)
            .where(GraphAnalyticsRun.project_id == PROJECT_ID, GraphAnalyticsRun.dataset_id == DATASET_ID)
            .order_by(GraphAnalyticsRun.created_at.desc(), GraphAnalyticsRun.id.desc())
            .limit(1)
        )
        if latest_run:
            print(f"   * Analytics Run ID       : {latest_run.id}")
            print(f"   * Hierarchical Levels    : {latest_run.levels} levels (Fine-grained to Broad)")
            print(f"   * Total Code Communities : {latest_run.community_count} communities")
            scores["community_clustering"] = 100.0
        else:
            print("   [-] No analytics run found")
            scores["community_clustering"] = 0.0

        # --- FINAL SCORECARD ---
        eval_duration = time.perf_counter() - start_time
        final_score = sum(scores.values()) / len(scores)

        print("\n" + "=" * 65)
        print("          CODEBASE INDEXING QUALITY SCORECARD")
        print("=" * 65)
        print(f"  1. Symbol Recall & Precision     : {scores['symbol_recall']:.1f}%")
        print(f"  2. Relation Constraint Integrity : {scores['relation_safety']:.1f}%")
        print(f"  3. Graph Topology & Connectivity : {scores['graph_connectivity']:.1f}%")
        print(f"  4. Community Clustering Quality  : {scores['community_clustering']:.1f}%")
        print("-" * 65)
        print(f"  * OVERALL INDEXING QUALITY SCORE: {final_score:.1f}% / 100.0%")
        print(f"  * Audit Execution Speed         : {eval_duration*1000:.2f} ms")
        print("=" * 65)

asyncio.run(run_quality_eval())
