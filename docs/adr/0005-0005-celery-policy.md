# ADR 0005: Celery delivery and idempotency

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

Tasks acknowledge late, reject on worker loss, prefetch one, and use explicit soft/hard limits. Only transient faults receive bounded exponential backoff with jitter. Database state and deterministic writes make at-least-once delivery safe; Redis is never authoritative.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
