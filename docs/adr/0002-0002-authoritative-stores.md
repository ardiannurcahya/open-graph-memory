# ADR 0002: Authoritative stores and projections

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

PostgreSQL owns metadata, lifecycle, authorization, and traces; S3-compatible storage owns source artifacts. Qdrant and Neo4j are derived projections and must be fully rebuildable.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
