from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_migration_0016_removes_embedding_states_with_linear_lineage() -> None:
    path = Path("apps/api/migrations/versions/0016_remove_embedding_states.py")
    spec = spec_from_file_location("migration_0016", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0016"
    assert migration.down_revision == "0015"
    assert "EMBEDDING" not in migration.DOCUMENT_STATES
    assert "EMBEDDING" not in migration.INDEXING_STAGES


def test_migration_0016_does_not_use_freshly_added_enum_values() -> None:
    source = Path("apps/api/migrations/versions/0016_remove_embedding_states.py").read_text()

    assert "WHERE status = 'EMBEDDING'" not in source
    assert "WHERE stage = 'EMBEDDING'" not in source
    assert "SET status = 'PERSISTING'" not in source
    assert "SET stage = 'PERSISTING'" not in source
    assert "::text" in source
    assert "CASE WHEN" in source
