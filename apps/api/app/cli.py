"""CLI tools for database operations."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


def get_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False)


@click.group()
def cli():
    """OGM operational tools."""
    pass


@cli.command()
@click.option("--out", "-o", required=True, help="Output file path")
@click.option("--format", "fmt", type=click.Choice(["sql", "custom"]), default="sql")
def backup(out: str, fmt: str):
    """Create database backup."""
    settings = get_settings()
    db_url = settings.database_url

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    if out_path.is_dir():
        out_path = out_path / f"ogm_backup_{timestamp}.sql"

    click.echo(f"Creating backup: {out_path}")

    pg_dump_cmd = ["pg_dump", db_url.replace("+asyncpg", "").replace("postgresql://", "")]

    if fmt == "custom":
        pg_dump_cmd.extend(["-Fc", "-f", str(out_path.with_suffix(".dump"))])
    else:
        pg_dump_cmd.extend(["-f", str(out_path)])

    try:
        subprocess.run(pg_dump_cmd, capture_output=True, text=True, check=True)
        click.echo(f"Backup completed: {out_path}")
    except subprocess.CalledProcessError as e:
        click.echo(f"Backup failed: {e.stderr}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("pg_dump not found. Install PostgreSQL client tools.", err=True)
        sys.exit(1)


@cli.command()
@click.option("--from", "from_file", required=True, help="Backup file path")
@click.option("--apply", is_flag=True, help="Actually restore (requires confirmation)")
def restore(from_file: str, apply: bool):
    """Restore database from backup."""
    from_path = Path(from_file)
    if not from_path.exists():
        click.echo(f"Backup file not found: {from_file}", err=True)
        sys.exit(1)

    settings = get_settings()
    db_url = settings.database_url

    if not apply:
        click.echo("DRY RUN: Would restore from", from_path)
        click.echo("Use --apply to actually restore")
        return

    click.echo(f"Restoring from: {from_path}")

    psql_cmd = ["psql", db_url.replace("+asyncpg", "").replace("postgresql://", "")]

    try:
        if from_path.suffix == ".dump":
            pg_restore_cmd = [
                "pg_restore",
                "-d", db_url.replace("+asyncpg", "").replace("postgresql://", ""),
                str(from_path),
            ]
            subprocess.run(pg_restore_cmd, capture_output=True, text=True, check=True)
        else:
            with open(from_path) as f:
                subprocess.run(
                    psql_cmd, stdin=f, capture_output=True, text=True, check=True
                )
        click.echo("Restore completed")
    except subprocess.CalledProcessError as e:
        click.echo(f"Restore failed: {e.stderr}", err=True)
        sys.exit(1)


@cli.command()
def integrity():
    """Check database integrity."""
    import asyncio

    async def _check():
        engine = get_engine()
        async with engine.connect() as conn:
            click.echo("Checking foreign key constraints...")
            result = await conn.execute(text("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_name;
            """))
            fk_count = result.rowcount
            click.echo(f"Found {fk_count} foreign key constraints")

            click.echo("\nChecking for orphaned records...")
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM agent_memory_episodes e
                WHERE NOT EXISTS (
                    SELECT 1 FROM projects p WHERE p.id = e.project_id
                );
            """))
            orphans = result.scalar()
            if orphans > 0:
                click.echo(f"WARNING: Found {orphans} orphaned episodes", err=True)
            else:
                click.echo("No orphaned episodes found")

            click.echo("\nChecking indexes...")
            result = await conn.execute(text("""
                SELECT indexname, tablename
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname;
            """))
            indexes = list(result)
            click.echo(f"Found {len(indexes)} indexes")

            click.echo("\nIntegrity check completed")

    asyncio.run(_check())


@cli.command()
@click.option("--apply", is_flag=True, help="Actually vacuum")
def vacuum(apply: bool):
    """Vacuum database to reclaim space."""
    import asyncio

    async def _vacuum():
        engine = get_engine()
        async with engine.connect() as conn:
            if not apply:
                result = await conn.execute(text("""
                    SELECT
                        relname,
                        n_dead_tup,
                        n_live_tup,
                        last_autovacuum
                    FROM pg_stat_user_tables
                    WHERE n_dead_tup > 0
                    ORDER BY n_dead_tup DESC;
                """))
                tables = list(result)
                if tables:
                    click.echo("Tables with dead tuples:")
                    for table in tables:
                        click.echo(f"  {table[0]}: {table[1]} dead / {table[2]} live")
                else:
                    click.echo("No dead tuples found")
                click.echo("\nUse --apply to actually vacuum")
                return

            click.echo("Running VACUUM ANALYZE...")
            await conn.execution_options(isolation_level="AUTOCOMMIT").execute(
                text("VACUUM ANALYZE;")
            )
            click.echo("Vacuum completed")

    asyncio.run(_vacuum())


@cli.command()
def fts_rebuild():
    """Rebuild full-text search indexes."""
    import asyncio

    async def _rebuild():
        engine = get_engine()
        async with engine.connect() as conn:
            click.echo("Rebuilding FTS indexes...")

            await conn.execute(text(
                "UPDATE agent_memory_episodes "
                "SET search_vector = to_tsvector('simple', "
                "title || ' ' || goal || ' ' || problem_signature) "
                "WHERE search_vector IS NULL;"
            ))

            await conn.execute(text("REINDEX INDEX ix_agent_memory_episodes_search;"))

            click.echo("FTS rebuild completed")

    asyncio.run(_rebuild())


@cli.command()
def checkpoint():
    """Truncate WAL (Write-Ahead Log)."""
    import asyncio

    async def _checkpoint():
        engine = get_engine()
        async with engine.connect() as conn:
            click.echo("Running CHECKPOINT...")
            await conn.execution_options(isolation_level="AUTOCOMMIT").execute(
                text("CHECKPOINT;")
            )
            click.echo("Checkpoint completed")

    asyncio.run(_checkpoint())


if __name__ == "__main__":
    cli()
