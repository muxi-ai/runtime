# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tree Search Method A - Pure LLM Tree Navigation
# Description:  Query-time retrieval over a document tree index via a single
#               LLM call (no embeddings touched)
# Role:         Retrieval-side component of reasoning-based RAG (Method A)
# Usage:        Invoked by KnowledgeHandler.search for tree-indexed sources
# Author:       Muxi Framework Team
#
# The compressed tree (titles + summaries only, never raw content) is
# injected into one LLM call together with the user query. The LLM reasons
# over structure - section names, summaries, sibling relationships - and
# returns the node_ids whose raw content most likely answers the query:
#
#   Output: {"thinking": "...", "node_list": ["0007", "0012"]}
#
# Selected node_ids are resolved to raw text from the tree's KV mapping and
# wrapped in the unified RetrievalResult schema.
#
# Failure isolation: any LLM/parse failure raises ``TreeNavigationError``;
# the caller falls back to vector search results - navigation failure never
# fails a user turn. Later phases add Method B (tree_search_b) and the
# hybrid runner (tree_search_hybrid) beside this module.
# =============================================================================

from typing import Any, List

from .tree_builder import extract_json_object
from .types import RetrievalResult, TreeIndex, TreeNavigationError

# Cap on raw content characters returned per selected node. Nodes are
# already bounded by ``max_tokens_per_node`` at build time; this is a
# second guard so a single selected parent node cannot flood the context.
_MAX_NODE_CONTENT_CHARS = 6000

_SYSTEM_PROMPT = (
    "You are a retrieval navigator for a hierarchical document tree index. "
    "Given the tree (node titles and summaries only) and a user query, select the "
    "node_ids whose raw content is most likely to answer the query. Prefer the most "
    "specific (deepest) relevant nodes. Select at most {max_nodes} node_ids. If any "
    "section could plausibly contain the answer, select it; only return an empty "
    "list when the document is clearly unrelated to the query. "
    'Respond ONLY with a JSON object of the form {{"thinking": "<brief reasoning>", '
    '"node_list": ["<node_id>", ...]}} where each node_id is the exact string from '
    "the tree. No markdown, no extra keys."
)


def _normalize_node_id(raw_id: Any) -> str:
    """Normalize an LLM-returned node id to the tree's zero-padded form."""
    node_id = str(raw_id).strip().strip('"')
    if node_id.isdigit() and len(node_id) < 4:
        return f"{int(node_id):04d}"
    return node_id


class TreeSearchA:
    """
    Method A retriever: one LLM call, structured output, KV resolution.

    Args:
        llm: Object exposing ``async chat(messages, **kwargs) -> str``
            (the runtime ``LLM`` class).
    """

    def __init__(self, llm: Any):
        self.llm = llm

    async def search(
        self, query: str, tree: TreeIndex, max_nodes: int = 3
    ) -> List[RetrievalResult]:
        """
        Navigate ``tree`` for ``query`` and return selected node contents.

        Raises:
            TreeNavigationError: On LLM failure or unusable structured output.
        """
        max_nodes = max(1, int(max_nodes))
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT.format(max_nodes=max_nodes)},
            {
                "role": "user",
                "content": f"Tree: {tree.compressed_json()}\nQuery: {query}",
            },
        ]

        try:
            # Notes:
            # - temperature 0.1 rather than 0.0: LLM.chat coerces falsy
            #   temperatures to the instance default (0.7).
            # - caching=False: navigation prompts over the same tree differ
            #   only by the (short) query, so the semantic response cache
            #   matches them as "similar" and replays node selections from
            #   previous, unrelated queries.
            response = await self.llm.chat(
                messages=messages,
                temperature=0.1,
                caching=False,
                metadata={"component": "knowledge_tree_search_a"},
            )
            parsed = extract_json_object(response)
        except Exception as e:
            raise TreeNavigationError(f"Tree navigation failed for '{tree.document}': {e}") from e

        node_list = parsed.get("node_list")
        if not isinstance(node_list, list):
            raise TreeNavigationError(
                f"Tree navigation returned no 'node_list' for '{tree.document}'"
            )

        results: List[RetrievalResult] = []
        for rank, raw_id in enumerate(node_list[:max_nodes]):
            node = tree.get_node(_normalize_node_id(raw_id))
            if node is None:
                continue  # hallucinated id - skip, keep the valid ones
            raw = self._resolve_content(tree, node)
            if not raw:
                continue
            results.append(
                RetrievalResult(
                    source_type="tree",
                    content=raw[:_MAX_NODE_CONTENT_CHARS],
                    # Rank-derived relevance: Method A has no similarity
                    # scores; earlier selections rank higher.
                    relevance=max(0.1, 1.0 - rank * 0.1),
                    metadata={
                        "document": tree.document,
                        "node_id": node.node_id,
                        "node_title": node.title,
                        "retrieval_method": "tree_a",
                    },
                    node_path=tree.node_path(node.node_id),
                )
            )
        return results

    @staticmethod
    def _resolve_content(tree: TreeIndex, node) -> str:
        """
        Resolve a selected node's raw content.

        Parent nodes only own their intro text (descendants own their
        spans), so when the navigator selects a parent, append the
        children's raw content until the per-node cap is reached.
        """
        parts = [tree.fetch_raw(node.node_id)]
        total = len(parts[0])
        if total < _MAX_NODE_CONTENT_CHARS:
            stack = list(node.sub_nodes)
            while stack and total < _MAX_NODE_CONTENT_CHARS:
                child = stack.pop(0)
                child_raw = tree.fetch_raw(child.node_id)
                if child_raw:
                    parts.append(child_raw)
                    total += len(child_raw)
                stack = list(child.sub_nodes) + stack
        return "\n\n".join(p for p in parts if p).strip()
