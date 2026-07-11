# ADR 0004: Stable identifiers and artifact versioning

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

Resources use UUID v7 values with readable prefixes. Derived artifact IDs are deterministic over source ID, source version, pipeline version, and artifact position. Provider, model, dimensions, preprocessing, prompt, and ontology versions accompany artifacts.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
