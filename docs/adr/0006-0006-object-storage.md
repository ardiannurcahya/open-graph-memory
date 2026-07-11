# ADR 0006: S3-compatible object storage boundary

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

Application code targets an ObjectStore contract and standard S3 semantics. RustFS is the repeatable local implementation; external S3-compatible endpoints are configuration-only substitutions. Object keys derive from stable IDs, never filenames.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
