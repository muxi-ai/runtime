"""Tests for batched storage in MemoryExtractor._process_extraction_results."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from muxi.runtime.services.memory.extractor import MemoryExtractor


class AddOnlyBackend:
    """Backend without a search method (no de-duplication support)."""

    def __init__(self):
        self.add = AsyncMock(return_value="mem-id")


def make_item(memory, collection="context", confidence=0.9, importance=0.5):
    return {
        "memory": memory,
        "confidence": confidence,
        "importance": importance,
        "collection": collection,
    }


def make_extractor(search_results=None, search_side_effect=None):
    long_term_memory = SimpleNamespace(
        search=AsyncMock(return_value=search_results or []),
        add=AsyncMock(return_value="mem-id"),
    )
    if search_side_effect is not None:
        long_term_memory.search.side_effect = search_side_effect

    overlord = SimpleNamespace(
        long_term_memory=long_term_memory,
        is_multi_user=False,
        current_agent=None,
        user_context_manager=SimpleNamespace(
            invalidate_identity_synopsis_cache=AsyncMock(return_value=None)
        ),
    )
    return MemoryExtractor(overlord=overlord)


@pytest.mark.asyncio
async def test_stores_all_non_duplicate_memories():
    extractor = make_extractor(search_results=[])
    results = {
        "extracted_info": [
            make_item("Works at TechCorp"),
            make_item("Enjoys hiking"),
            make_item("Has a sister in Boston"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    ltm = extractor.overlord.long_term_memory
    assert ltm.search.await_count == 3
    assert ltm.add.await_count == 3
    stored = {call.kwargs["content"] for call in ltm.add.await_args_list}
    assert stored == {"Works at TechCorp", "Enjoys hiking", "Has a sister in Boston"}


@pytest.mark.asyncio
async def test_skips_semantically_similar_memory():
    # Score above 1/(1+0.3) ~= 0.769 means duplicate
    extractor = make_extractor(search_results=[{"text": "Works at TechCorp", "score": 0.95}])
    results = {"extracted_info": [make_item("Works at TechCorp")]}

    await extractor._process_extraction_results(results, user_id="user-1")

    assert extractor.overlord.long_term_memory.add.await_count == 0


@pytest.mark.asyncio
async def test_stores_dissimilar_memory():
    # Score below the threshold means the memory is stored
    extractor = make_extractor(search_results=[{"text": "Something else", "score": 0.5}])
    results = {"extracted_info": [make_item("Works at TechCorp")]}

    await extractor._process_extraction_results(results, user_id="user-1")

    assert extractor.overlord.long_term_memory.add.await_count == 1


@pytest.mark.asyncio
async def test_deduplicates_identical_facts_within_batch():
    # The serial implementation added each memory before checking the next
    # one, so an in-batch duplicate matched the freshly-added memory. With
    # concurrent checks the batch is collapsed in Python instead.
    extractor = make_extractor(search_results=[])
    results = {
        "extracted_info": [
            make_item("Works at TechCorp"),
            make_item("works at   TechCorp"),  # same fact, different spacing/case
            make_item("Enjoys hiking"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    ltm = extractor.overlord.long_term_memory
    assert ltm.search.await_count == 2
    assert ltm.add.await_count == 2


@pytest.mark.asyncio
async def test_invalidates_identity_synopsis_cache_once_per_batch():
    extractor = make_extractor(search_results=[])
    results = {
        "extracted_info": [
            make_item("Is a software engineer", collection="user_identity"),
            make_item("Has a sister in Boston", collection="relationships"),
            make_item("Working on project X", collection="work_projects"),
            make_item("Enjoys hiking", collection="context"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    invalidate = extractor.overlord.user_context_manager.invalidate_identity_synopsis_cache
    assert invalidate.await_count == 1
    invalidate.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_no_cache_invalidation_without_identity_memories():
    extractor = make_extractor(search_results=[])
    results = {"extracted_info": [make_item("Enjoys hiking", collection="context")]}

    await extractor._process_extraction_results(results, user_id="user-1")

    invalidate = extractor.overlord.user_context_manager.invalidate_identity_synopsis_cache
    assert invalidate.await_count == 0


@pytest.mark.asyncio
async def test_search_failure_skips_fact_but_stores_others():
    async def search_side_effect(**kwargs):
        if kwargs["query"] == "Enjoys hiking":
            raise RuntimeError("search backend down")
        return []

    extractor = make_extractor(search_side_effect=search_side_effect)
    results = {
        "extracted_info": [
            make_item("Works at TechCorp"),
            make_item("Enjoys hiking"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    ltm = extractor.overlord.long_term_memory
    assert ltm.add.await_count == 1
    assert ltm.add.await_args.kwargs["content"] == "Works at TechCorp"


@pytest.mark.asyncio
async def test_add_failure_does_not_block_other_adds():
    extractor = make_extractor(search_results=[])

    async def add_side_effect(**kwargs):
        if kwargs["content"] == "Works at TechCorp":
            raise RuntimeError("db write failed")
        return "mem-id"

    extractor.overlord.long_term_memory.add.side_effect = add_side_effect
    results = {
        "extracted_info": [
            make_item("Works at TechCorp"),
            make_item("Enjoys hiking"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    assert extractor.overlord.long_term_memory.add.await_count == 2


@pytest.mark.asyncio
async def test_backend_without_search_stores_everything():
    extractor = make_extractor()
    extractor.overlord.long_term_memory = AddOnlyBackend()
    results = {
        "extracted_info": [
            make_item("Works at TechCorp"),
            make_item("Enjoys hiking"),
        ]
    }

    await extractor._process_extraction_results(results, user_id="user-1")

    assert extractor.overlord.long_term_memory.add.await_count == 2


@pytest.mark.asyncio
async def test_below_confidence_threshold_skipped():
    extractor = make_extractor(search_results=[])
    results = {"extracted_info": [make_item("Works at TechCorp", confidence=0.1)]}

    await extractor._process_extraction_results(results, user_id="user-1")

    assert extractor.overlord.long_term_memory.add.await_count == 0
