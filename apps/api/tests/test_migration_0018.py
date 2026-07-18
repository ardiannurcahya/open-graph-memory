from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.graph_models import (
    EntityAliasEvidence,
    GraphConsolidationRun,
    GraphExtractionRun,
)


def test_document_consolidation_migration_matches_models() -> None:
    path = Path("apps/api/migrations/versions/0018_document_graph_consolidation.py")
    spec = spec_from_file_location("document_graph_consolidation", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "0017"
    assert "raw_extraction" in GraphExtractionRun.__table__.c
    assert GraphConsolidationRun.__tablename__ == "graph_consolidation_runs"
    assert set(EntityAliasEvidence.__table__.primary_key.columns.keys()) == {
        "alias_id",
        "evidence_id",
    }
