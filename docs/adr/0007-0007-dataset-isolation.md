# ADR 0007: Project and dataset isolation

- Status: Accepted; amended by the graph-only architecture
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

Authentication uses admin and project API keys in X-API-Key. Every applicable SQL row, object key, and graph node/query carries project_id and dataset_id. Missing scope is a defect; workspace_id is reserved. Vector payloads and filters were subject to the same rule before the graph-only architecture removed the vector projection.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
