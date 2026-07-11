# ADR 0008: Provider adapter capabilities

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

Chat and embedding registries and credentials remain separate. Adapters declare supported parameters and capabilities, normalize outputs and errors, and omit unsupported options. OpenAI-compatible chat/embedding and Anthropic-compatible chat are initial boundaries, not Milestone 0 integrations.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
