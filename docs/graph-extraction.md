# Graph extraction core

M3 starts with PostgreSQL as the authoritative graph-artifact store. Extraction runs retain provider, model, prompt, ontology, input hash, and chunk/document/dataset/project provenance. Entities never merge across datasets; normalized name plus type only identifies a candidate and ambiguous matches remain unresolved.

## Deterministic fixtures

`DeterministicExtractor` recognizes `Name [Type]` and `Source -> RELATION -> Target`. It is intentionally narrow and repeatable for tests, not production NLP.

## OpenAI-compatible adapter

`OpenAICompatibleExtractor` accepts a base URL, API key, model, prompt version, and timeout. It requests strict JSON Schema output with temperature zero. Configure secrets in the caller; the core does not read environment variables or persist credentials.

## Future work

Neo4j projection, background orchestration, HTTP APIs, review UI, and fuzzy/entity-model resolution are deliberately outside this increment.
