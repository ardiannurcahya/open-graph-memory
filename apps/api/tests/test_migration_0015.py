from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def load_migration() -> ModuleType:
    path = Path("apps/api/migrations/versions/0015_drop_obsolete_runtime_tables.py")
    spec = spec_from_file_location("migration_0015", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_0015_has_linear_lineage_and_preserves_graph_analytics() -> None:
    migration = load_migration()
    source = Path(migration.__file__).read_text(encoding="utf-8")

    assert migration.revision == "0015"
    assert migration.down_revision == "0014"
    assert migration.TABLES == (
        "query_logs",
        "memory_users",
        "memory_agents",
        "memory_sessions",
        "memory_messages",
        "memory_facts",
        "community_report_jobs",
        "community_report_outbox",
        "community_reports",
        "community_report_evidence",
    )
    assert "op.drop_table(\"graph_analytics" not in source


def test_migration_0015_uses_dependency_ordered_drops() -> None:
    source = Path(load_migration().__file__).read_text(encoding="utf-8")
    upgrade = source[source.index("def upgrade()") : source.index("def downgrade()")]
    expected = [
        "community_report_evidence",
        "community_reports",
        "community_report_outbox",
        "community_report_jobs",
        "memory_facts",
        "memory_messages",
        "memory_sessions",
        "memory_agents",
        "memory_users",
        "query_logs",
    ]

    positions = [upgrade.index(f'op.drop_table(\"{table}\")') for table in expected]
    assert positions == sorted(positions)
    assert "CREATE TABLE" not in upgrade


def test_migration_0015_downgrade_restores_constraints_indexes_types_and_data() -> None:
    source = Path(load_migration().__file__).read_text(encoding="utf-8")
    downgrade = source[source.index("def downgrade()") :]

    for name in (
        "ix_query_logs_scope_created",
        "uq_memory_users_project_external",
        "uq_memory_agents_project_name",
        "ix_memory_sessions_scope",
        "ix_memory_messages_session_created",
        "ix_memory_facts_scope_status",
        "ix_memory_facts_subject",
        "uq_community_report_job_input",
        "ix_community_report_jobs_scope",
        "ix_community_report_jobs_dispatch",
        "uq_community_report_job",
        "ix_community_reports_scope",
        "uq_community_report_evidence",
        "ck_community_report_jobs_level",
        "ck_community_reports_level",
    ):
        assert name in downgrade
    assert 'name="memory_fact_status"' in source
    assert 'name="community_report_status"' in source
    assert "_backup_0015" not in source


def test_obsolete_runtime_models_and_settings_are_removed() -> None:
    from app.config import Settings
    from app.models import Base

    obsolete_tables = {
        "query_logs",
        "memory_users",
        "memory_agents",
        "memory_sessions",
        "memory_messages",
        "memory_facts",
        "community_report_jobs",
        "community_report_outbox",
        "community_reports",
        "community_report_evidence",
    }

    assert obsolete_tables.isdisjoint(Base.metadata.tables)
    assert not any(name.startswith("community_report_") for name in Settings.model_fields)
    assert {
        "graph_analytics_runs",
        "graph_analytics_memberships",
        "graph_analytics_entity_metrics",
        "graph_analytics_communities",
    } <= set(Base.metadata.tables)
