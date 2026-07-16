# ADR 0002: Authoritative stores and projections

- Status: Superseded by the graph-only architecture
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

PostgreSQL owns metadata, lifecycle, authorization, and traces; S3-compatible storage owns source artifacts. At the time of this decision, Qdrant and Neo4j were derived projections and had to be fully rebuildable. The current graph-only architecture removes Qdrant; Neo4j remains a rebuildable projection.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
