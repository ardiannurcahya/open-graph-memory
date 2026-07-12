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
        ranked: list[tuple[int, str]] = []
        for block in evidence.split("\n\n"):
            words = set(self._tokens(block))
            ranked.append((len(terms.intersection(words)), block))
        score, matching = max(ranked, default=(0, ""), key=lambda item: item[0])
        # A single distinctive term is sufficient for terse questions, and policy
        # questions commonly paraphrase a heading while sharing only its subject.
        policy_question = "policy" in self._tokens(question)
        required_score = 1 if len(terms) <= 1 or policy_question else 2
        coverage = score / max(1, len(terms))
        requirement_question = "require" in terms
        supported = coverage >= 0.5 if requirement_question else score >= 3 or score == len(terms)
        if score >= required_score and (required_score == 1 or supported) and matching:
            citation = re.match(r"\[(\d+)]", matching)
            index = citation.group(1) if citation else ""
            answer = f"Based on the supplied evidence {matching.splitlines()[-1]} [{index}]."
        else:
            answer = "I cannot answer from the supplied evidence."
        return ChatResult(answer, Usage(len(context.split()), len(answer.split())))
