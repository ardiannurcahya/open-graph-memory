import asyncio

from app.providers import DeterministicProvider


def test_embedding_ignores_punctuation_and_normalizes_inflections() -> None:
    provider = DeterministicProvider()
    vectors = asyncio.run(provider.embed(["files indexing?", "file index"]))
    assert vectors[0] == vectors[1]


def test_chat_answers_upload_types_and_refuses_unrelated_question() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=a document_id=a
Document upload accepts UTF-8 TXT, Markdown, HTML, CSV, and valid PDF files.

[2] chunk_id=b document_id=b
Providers must support embeddings and chat completion with usage reporting.
"""
    answer = asyncio.run(provider.chat([
        {"role": "system", "content": context},
        {"role": "user", "content": "Which file types can document upload accept?"},
    ])).text
    refused = asyncio.run(provider.chat([
        {"role": "system", "content": context},
        {"role": "user", "content": "What was revenue last quarter?"},
    ])).text
    assert "[1]" in answer
    assert "cannot answer" in refused.lower()


def test_chat_answers_subject_role_requirement_and_version_questions() -> None:
    provider = DeterministicProvider()
    cases = [
        ("What role does Redis have?", "Redis is the Celery broker and result backend."),
        (
            "What provider capabilities are required?",
            "Providers must support embeddings and chat completion with usage reporting.",
        ),
        ("What Python version is required?", "The project requires Python 3.13."),
    ]
    for question, evidence in cases:
        result = asyncio.run(provider.chat([
            {"role": "system", "content": f"Evidence:\n[1] chunk_id=a\n{evidence}"},
            {"role": "user", "content": question},
        ])).text
        assert "[1]" in result
        assert "cannot answer" not in result.lower()


def test_chat_refuses_unsupported_wh_questions_despite_incidental_overlap() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=a
Providers must support production embeddings and chat completion.

[2] chunk_id=b
The API service uses private configuration values.
"""
    questions = [
        "What is the CEO's home address?",
        "What was revenue last quarter?",
        "Which GPU model runs production embeddings?",
        "What is the private API key?",
    ]
    for question in questions:
        result = asyncio.run(provider.chat([
            {"role": "system", "content": context},
            {"role": "user", "content": question},
        ])).text
        assert "cannot answer" in result.lower()