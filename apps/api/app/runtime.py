from dataclasses import dataclass

from app.providers import ChatProvider, EmbeddingProvider
from app.vector_store import VectorStore


@dataclass(frozen=True)
class Runtime:
    embeddings: EmbeddingProvider
    chat: ChatProvider
    vectors: VectorStore


_runtime: Runtime | None = None


def install_runtime(runtime: Runtime) -> None:
    global _runtime
    if _runtime is not None:
        raise RuntimeError("runtime already initialized")
    _runtime = runtime


def clear_runtime() -> None:
    global _runtime
    _runtime = None


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("application runtime is not initialized")
    return _runtime


def get_embedding_provider() -> EmbeddingProvider:
    return get_runtime().embeddings


def get_chat_provider() -> ChatProvider:
    return get_runtime().chat


def get_vector_store() -> VectorStore:
    return get_runtime().vectors
