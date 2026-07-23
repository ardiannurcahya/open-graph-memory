"""Authoritative, scoped graph garbage collection after document evidence is removed."""

from uuid import UUID

from sqlalchemy import select
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
    # 1. Collect entity and relation IDs touched by this document's evidence.
    doc_evidence = list(
        await db.scalars(
            select(GraphEvidence).where(
                GraphEvidence.project_id == project_id,
                GraphEvidence.dataset_id == dataset_id,
                GraphEvidence.document_id == document_id,
            )
        )
    )
    affected_entity_ids = {ev.entity_id for ev in doc_evidence if ev.entity_id is not None}
    affected_relation_ids = {ev.relation_id for ev in doc_evidence if ev.relation_id is not None}

    for item in doc_evidence:
        await db.delete(item)
    await db.flush()

    # 2. Remove aliases that lost all evidence (scoped to affected entities only).
    if affected_entity_ids:
        aliases = list(
            await db.scalars(
                select(EntityAlias).where(
                    EntityAlias.project_id == project_id,
                    EntityAlias.dataset_id == dataset_id,
                    EntityAlias.entity_id.in_(affected_entity_ids),
                )
            )
        )
        alias_ids = {a.id for a in aliases}
        if alias_ids:
            supported_ids = set(
                await db.scalars(
                    select(EntityAliasEvidence.alias_id).where(
                        EntityAliasEvidence.alias_id.in_(alias_ids)
                    )
                )
            )
            for alias in aliases:
                if alias.id not in supported_ids:
                    await db.delete(alias)
        await db.flush()

    # 3. Remove relations that lost all evidence (scoped to affected relations only).
    if affected_relation_ids:
        relations = list(
            await db.scalars(
                select(RelationAssertion).where(
                    RelationAssertion.project_id == project_id,
                    RelationAssertion.dataset_id == dataset_id,
                    RelationAssertion.id.in_(affected_relation_ids),
                )
            )
        )
        rel_ids = {r.id for r in relations}
        if rel_ids:
            supported_rel_ids = set(
                await db.scalars(
                    select(GraphEvidence.relation_id).where(
                        GraphEvidence.relation_id.in_(rel_ids)
                    )
                )
            )
            for relation in relations:
                if relation.id not in supported_rel_ids:
                    await db.delete(relation)
        await db.flush()

    # 4. Remove entities that lost all evidence AND all relations.
    #    Use a broader scope: affected entities + entities referenced by affected relations.
    candidate_entity_ids = set(affected_entity_ids)
    if affected_relation_ids:
        for rel in (await db.scalars(
            select(RelationAssertion).where(
                RelationAssertion.project_id == project_id,
                RelationAssertion.dataset_id == dataset_id,
                RelationAssertion.id.in_(affected_relation_ids),
            )
        )).all():
            candidate_entity_ids.add(rel.source_entity_id)
            candidate_entity_ids.add(rel.target_entity_id)

    if not candidate_entity_ids:
        return

    entities = list(
        await db.scalars(
            select(CanonicalEntity).where(
                CanonicalEntity.project_id == project_id,
                CanonicalEntity.dataset_id == dataset_id,
                CanonicalEntity.id.in_(candidate_entity_ids),
            )
        )
    )

    # Batch check: which entities still have evidence?
    entity_ids_set = {e.id for e in entities}
    supported_entity_ids = set(
        await db.scalars(
            select(GraphEvidence.entity_id).where(
                GraphEvidence.entity_id.in_(entity_ids_set)
            )
        )
    )

    # Batch check: which entities still have relations?
    related_entity_ids = set(
        await db.scalars(
            select(RelationAssertion.source_entity_id).where(
                RelationAssertion.source_entity_id.in_(entity_ids_set)
            )
        )
    ) | set(
        await db.scalars(
            select(RelationAssertion.target_entity_id).where(
                RelationAssertion.target_entity_id.in_(entity_ids_set)
            )
        )
    )

    unsupported = [
        e for e in entities
        if e.id not in supported_entity_ids and e.id not in related_entity_ids
    ]
    unsupported_ids = {entity.id for entity in unsupported}
    if not unsupported_ids:
        return

    # Check merge history to protect entities linked to survivors.
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
    if removable_ids:
        rem_aliases = list(
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
        for alias in rem_aliases:
            await db.delete(alias)
        for entity in unsupported:
            if entity.id in removable_ids:
                await db.delete(entity)
    await db.flush()
