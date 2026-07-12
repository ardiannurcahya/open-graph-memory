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
    answer = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {"role": "user", "content": "Which file types can document upload accept?"},
            ]
        )
    ).text
    refused = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {"role": "user", "content": "What was revenue last quarter?"},
            ]
        )
    ).text
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
        result = asyncio.run(
            provider.chat(
                [
                    {"role": "system", "content": f"Evidence:\n[1] chunk_id=a\n{evidence}"},
                    {"role": "user", "content": question},
                ]
            )
        ).text
        assert "[1]" in result
        assert "cannot answer" not in result.lower()


def test_chat_selects_supported_relation_claims_and_cites_each_claim() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=people
Acme Labs -> EMPLOYS -> Alice Nguyen

[2] chunk_id=product
Atlas -> BUILT_BY -> Acme Labs

[3] chunk_id=followup
Alice Nguyen -> LEADS -> Atlas
"""
    result = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {"role": "user", "content": "Who leads Atlas and who built Atlas?"},
            ]
        )
    ).text
    assert "Alice Nguyen -> LEADS -> Atlas [3]" in result
    assert "Atlas -> BUILT_BY -> Acme Labs [2]" in result
    assert "[1]" not in result


def test_chat_handles_inverse_build_and_multi_hop_relation_questions() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=product
Atlas -> BUILT_BY -> Acme Labs

[2] chunk_id=followup
Alice Nguyen -> LEADS -> Atlas
"""
    questions = (
        ("What product did Acme Labs build?", ("[1]",)),
        ("Which organization built the product led by Alice Nguyen?", ("[1]", "[2]")),
    )
    for question, citations in questions:
        result = asyncio.run(
            provider.chat(
                [{"role": "system", "content": context}, {"role": "user", "content": question}]
            )
        ).text
        assert "cannot answer" not in result.lower()
        assert all(citation in result for citation in citations)


def test_chat_refuses_relation_not_asserted_by_matching_entities() -> None:
    provider = DeterministicProvider()
    context = "Evidence:\n[1] chunk_id=a\nAcme Labs [Organization]\\nAtlas [Product]"
    result = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {"role": "user", "content": "Does Acme Labs own Atlas?"},
            ]
        )
    ).text
    assert "cannot answer" in result.lower()


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
        result = asyncio.run(
            provider.chat(
                [
                    {"role": "system", "content": context},
                    {"role": "user", "content": question},
                ]
            )
        ).text
        assert "cannot answer" in result.lower()


def test_chat_refuses_ambiguous_types_and_unsupported_entity_relation() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=ambiguous
Jordan [Person]
Jordan [Organization]
Jordan -> ADVISES -> Acme Labs

[2] chunk_id=people
Acme Labs -> EMPLOYS -> Alice Nguyen
"""
    for question in ("Is Jordan a person or an organization?", "Does Acme Labs employ Eve?"):
        result = asyncio.run(
            provider.chat(
                [{"role": "system", "content": context}, {"role": "user", "content": question}]
            )
        ).text
        assert "cannot answer" in result.lower()


def test_chat_answers_cycles_and_fanout_with_all_supporting_citations() -> None:
    provider = DeterministicProvider()
    context = """Evidence:
[1] chunk_id=people
Acme Labs -> EMPLOYS -> Alice Nguyen

[2] chunk_id=product
Atlas -> BUILT_BY -> Acme Labs

[3] chunk_id=followup
Alice Nguyen -> LEADS -> Atlas
"""
    cycle = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {
                    "role": "user",
                    "content": "Starting at Atlas, what supported relations return to Atlas?",
                },
            ]
        )
    ).text
    fanout = asyncio.run(
        provider.chat(
            [
                {"role": "system", "content": context},
                {"role": "user", "content": "List all supported relations connected to Acme Labs."},
            ]
        )
    ).text
    assert all(f"[{index}]" in cycle for index in ("1", "2", "3"))
    assert all(f"[{index}]" in fanout for index in ("1", "2"))
    assert "[3]" not in fanout
