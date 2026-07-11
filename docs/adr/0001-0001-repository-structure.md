# ADR 0001: Repository and package structure

- Status: Accepted
- Date: 2025-02-24

## Context

Milestone 0 requires a durable boundary before feature implementation.

## Decision

A monorepo separates deployable API and web applications under `apps`, reusable Python code under `packages`, infrastructure under `deployments`, and operational tooling under `scripts`. Python uses one root uv project; web remains an npm package.

## Consequences

Future milestones must preserve this contract or supersede it with a new ADR. The added discipline improves recovery and portability at the cost of explicit scoping and version metadata.
