"""Authoritative, scoped graph garbage collection after document evidence is removed."""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_models import (
    CanonicalEntity,
    EntityAlias,
    EntityAliasEvidence,
    EntityMergeHistory,
    GraphEvidence,
    RelationAssertion,
)


async def cleanup_document_graph(
    db: AsyncSession, project_id: UUID, dataset_id: str, document_id: str
) -> None:
    """Remove graph subjects made unsupported by one document without crossing its scope."""
    evidence = list(
        await db.scalars(
            select(GraphEvidence)
            .where(
                GraphEvidence.project_id == project_id,
                GraphEvidence.dataset_id == dataset_id,
                GraphEvidence.document_id == document_id,
            )
            .with_for_update()
        )
    )
    for item in evidence:
        await db.delete(item)
    await db.flush()

    aliases = list(
        await db.scalars(
            select(EntityAlias).where(
                EntityAlias.project_id == project_id,
                EntityAlias.dataset_id == dataset_id,
            )
        )
    )
    for alias in aliases:
        supported = await db.scalar(
            select(exists().where(EntityAliasEvidence.alias_id == alias.id))
        )
        if not supported:
            await db.delete(alias)
    await db.flush()

    relations = list(
        await db.scalars(
            select(RelationAssertion)
            .where(
                RelationAssertion.project_id == project_id,
                RelationAssertion.dataset_id == dataset_id,
            )
            .with_for_update()
        )
    )
    for relation in relations:
        supported = await db.scalar(
            select(exists().where(GraphEvidence.relation_id == relation.id))
        )
        if not supported:
            await db.delete(relation)
    await db.flush()

    entities = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == project_id,
                CanonicalEntity.dataset_id == dataset_id,
            )
            .with_for_update()
        )
    )
    unsupported: list[CanonicalEntity] = []
    for entity in entities:
        has_evidence = await db.scalar(select(exists().where(GraphEvidence.entity_id == entity.id)))
        has_relation = await db.scalar(
            select(
                exists().where(
                    (RelationAssertion.source_entity_id == entity.id)
                    | (RelationAssertion.target_entity_id == entity.id)
                )
            )
        )
        if not has_evidence and not has_relation:
            unsupported.append(entity)

    unsupported_ids = {entity.id for entity in unsupported}
    if unsupported_ids:
        merges = list(
            await db.scalars(
                select(EntityMergeHistory).where(
                    EntityMergeHistory.project_id == project_id,
                    EntityMergeHistory.dataset_id == dataset_id,
                    (EntityMergeHistory.source_entity_id.in_(unsupported_ids))
                    | (EntityMergeHistory.target_entity_id.in_(unsupported_ids)),
                )
            )
        )
        # Retain a merge and its unsupported endpoint when it still references a survivor.
        removable_merges = [
            merge
            for merge in merges
            if merge.source_entity_id in unsupported_ids
            and merge.target_entity_id in unsupported_ids
        ]
        protected_ids = {
            entity_id
            for merge in merges
            if merge not in removable_merges
            for entity_id in (merge.source_entity_id, merge.target_entity_id)
        }
        removable_ids = unsupported_ids - protected_ids
        aliases = list(
            await db.scalars(
                select(EntityAlias).where(
                    EntityAlias.project_id == project_id,
                    EntityAlias.dataset_id == dataset_id,
                    EntityAlias.entity_id.in_(removable_ids),
                )
            )
        )
        for merge in removable_merges:
            await db.delete(merge)
        for alias in aliases:
            await db.delete(alias)
        for entity in unsupported:
            if entity.id in removable_ids:
                await db.delete(entity)
    await db.flush()
