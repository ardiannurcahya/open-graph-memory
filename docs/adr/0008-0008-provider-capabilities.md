# ADR 0008: Provider adapter capabilities

- Status: Superseded by the graph-only architecture
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

At the time of this decision, chat and embedding registries and credentials were separate. Adapters declared supported parameters and capabilities, normalized outputs and errors, and omitted unsupported options. OpenAI-compatible chat/embedding and Anthropic-compatible chat were initial boundaries, not Milestone 0 integrations. The current graph-only architecture removes chat and embedding providers; graph extraction remains the only model-provider boundary.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
