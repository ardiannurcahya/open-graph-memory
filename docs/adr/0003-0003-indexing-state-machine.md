# ADR 0003: Document and indexing state machine

- Status: Superseded by the graph-only architecture
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

At the time of this decision, documents progressed through uploaded, queued, parsing, chunking, embedding, persisting, and indexed. Failed, cancelled, and stale were explicit terminal or recovery states. Transitions, attempts, pipeline version, and sanitized errors lived in PostgreSQL. The current graph-only architecture removes the embedding state and transitions from chunking to persisting.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
