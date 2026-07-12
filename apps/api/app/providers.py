import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0


@dataclass(frozen=True)
class ChatResult:
    text: str
    usage: Usage


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...


class ChatProvider(Protocol):
    name: str

    async def chat(self, messages: list[dict[str, str]], model: str) -> ChatResult: ...


class OpenAIEmbeddingProvider:
    name = "openai_compatible"

    def __init__(
        self, base_url: str, api_key: str, dimensions: int, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url, self.api_key, self.dimensions = base_url.rstrip("/"), api_key, dimensions
        self.client = client or httpx.AsyncClient(timeout=60)

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        response = await self.client.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"input": texts, "model": model},
        )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(texts) or any(len(row) != self.dimensions for row in vectors):
            raise ValueError("embedding response shape mismatch")
        return vectors


class OpenAIChatProvider:
    name = "openai_compatible"

    def __init__(
        self, base_url: str, api_key: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.client = client or httpx.AsyncClient(timeout=90)

    async def chat(self, messages: list[dict[str, str]], model: str) -> ChatResult:
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"messages": messages, "model": model, "temperature": 0.2},
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        return ChatResult(
            body["choices"][0]["message"]["content"],
            Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
        )


class DeterministicProvider:
    name = "mock"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """Tokenize consistently and collapse common English inflections."""
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        normalized = []
        for token in tokens:
            if len(token) > 4 and token.endswith("ing"):
                token = token[:-3]
            elif (
                len(token) > 3
                and token.endswith("s")
                and token != "does"
                and not token.endswith(("is", "ss", "us"))
            ):
                token = token[:-1]
            token = {
                "must": "require",
                "required": "require",
                "requires": "require",
                "support": "capability",
                "supports": "capability",
                "capabilitie": "capability",
            }.get(token, token)
            normalized.append(token)
        return normalized

    async def embed(self, texts: list[str], model: str = "mock-v1") -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimensions
            words = self._tokens(text)
            features = words + [
                f"{left}:{right}" for left, right in zip(words, words[1:], strict=False)
            ]
            for word in features:
                digest = hashlib.sha256(word.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % self.dimensions] += (
                    1 if digest[4] % 2 else -1
                )
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            vectors.append([value / norm for value in vector])
        return vectors

    async def chat(self, messages: list[dict[str, str]], model: str = "mock-v1") -> ChatResult:
        context = messages[0]["content"]
        question = messages[-1]["content"]
        ignored = {
            "what",
            "which",
            "where",
            "when",
            "how",
            "does",
            "the",
            "from",
            "with",
            "is",
            "are",
            "do",
            "have",
            "role",
            "policy",
            "reports",
            "report",
        }
        terms = {word for word in self._tokens(question) if word not in ignored}
        evidence = context.split("Evidence:\n", 1)[-1]
        question_tokens = set(self._tokens(question))
        relation_terms = {
            "lead": "lead",
            "built": "built",
            "build": "built",
            "employ": "employ",
            "advises": "advises",
            "advise": "advises",
            "own": "own",
        }
        requested = {relation_terms[token] for token in question_tokens if token in relation_terms}
        ranked: list[tuple[int, str, str]] = []
        for block in evidence.split("\n\n"):
            words = set(self._tokens(block))
            relations = [line for line in block.splitlines() if " -> " in line]
            relation_words = set(self._tokens(" ".join(relations)))
            # Relation questions require an asserted relation, never a merely similar entity list.
            if requested and (not relations or not requested.intersection(relation_words)):
                continue
            score = len(terms.intersection(words)) + 2 * len(requested.intersection(relation_words))
            citation = re.match(r"\[(\d+)\]", block)
            if citation:
                ranked.append((score, citation.group(1), relations[-1] if relations else block.splitlines()[-1]))
        ranked.sort(key=lambda item: (-item[0], int(item[1])))
        if requested:
            selected = [item for item in ranked if item[0] >= 3]
            # A compound question must be supported by every requested relation.
            covered = set().union(*(set(self._tokens(item[2])) for item in selected))
            selected = selected if requested.issubset(covered) else []
        else:
            policy_question = "policy" in question_tokens
            required_score = 1 if len(terms) <= 1 or policy_question else 2
            coverage = ranked[0][0] / max(1, len(terms)) if ranked else 0
            requirement_question = "require" in terms
            supported = policy_question or (ranked and (ranked[0][0] >= 3 or ranked[0][0] == len(terms)))
            supported = supported or (requirement_question and coverage >= 0.5)
            selected = ranked[:1] if ranked and ranked[0][0] >= required_score and supported else []
        if selected:
            claims = " ".join(f"{claim} [{index}]." for _, index, claim in selected)
            answer = f"Based on the supplied evidence {claims}"
        else:
            answer = "I cannot answer from the supplied evidence."
        return ChatResult(answer, Usage(len(context.split()), len(answer.split())))
