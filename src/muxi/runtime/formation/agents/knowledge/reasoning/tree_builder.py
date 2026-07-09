# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tree Builder - LLM-Assisted Hierarchical Document Indexing
# Description:  Builds a per-document tree index (structural ToC optimized for
#               LLM reasoning) at knowledge-ingestion time
# Role:         Ingestion-side component of reasoning-based RAG (Method A)
# Usage:        Invoked by KnowledgeHandler when a knowledge file crosses the
#               reasoning token threshold (or declares ``retrieval: tree``)
# Author:       Muxi Framework Team
#
# The builder runs in two passes:
#
# 1. Structural pass (deterministic, no LLM): the document is segmented into
#    a hierarchy using markdown/ATX headings when present, or fixed
#    token-window "pages" otherwise. Node boundaries are recorded as
#    character offsets (``start_index`` / ``end_index``) into the extracted
#    text. Oversized leaves are split into part-windows so every node's raw
#    content stays under ``max_tokens_per_node``.
#
# 2. Summary pass (LLM): node titles + excerpts are sent to the tree model
#    in batches; the LLM returns one navigation-oriented summary per node.
#    These summaries are what Method A reasons over at query time.
#
# Failure isolation: any LLM or parsing failure raises ``TreeBuildError``;
# the caller (KnowledgeHandler) falls back to the vector pipeline and emits
# ``KNOWLEDGE_TREE_FALLBACK_TO_VECTOR`` - a build failure never fails
# formation load.
# =============================================================================

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .....utils.fastjson import json
from .types import DEFAULT_TREE_SETTINGS, TreeBuildError, TreeIndex, TreeNode

# Approximate characters-per-token ratio used for cheap size estimates and
# for the tokenizer-unavailable fallback.
_CHARS_PER_TOKEN = 4

# Max nodes summarized per LLM call. Keeps each request comfortably inside
# cheap-model context windows even with 400-char excerpts per node.
_SUMMARY_BATCH_SIZE = 40

# Excerpt length (chars) included per node in the summary prompt.
_EXCERPT_CHARS = 400

# Cached tiktoken encoder (lazy; tiktoken is an optional transitive dep).
_TOKEN_ENCODER: Optional[Any] = None
_TOKEN_ENCODER_FAILED = False


def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken when available, ``len // 4`` otherwise.

    The threshold gate only needs order-of-magnitude accuracy; the char
    heuristic keeps the gate working when tiktoken is not installed.
    """
    global _TOKEN_ENCODER, _TOKEN_ENCODER_FAILED
    if not text:
        return 0
    if _TOKEN_ENCODER is None and not _TOKEN_ENCODER_FAILED:
        try:
            import tiktoken

            _TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _TOKEN_ENCODER_FAILED = True
    if _TOKEN_ENCODER is not None:
        try:
            return len(_TOKEN_ENCODER.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class _Section:
    """Intermediate structural segment produced by the deterministic pass."""

    title: str
    level: int  # heading depth (1-based); 0 = synthetic window
    start: int  # char offset (inclusive)
    end: int  # char offset (exclusive)
    children: List["_Section"] = field(default_factory=list)


# ATX headings: ``# Title`` .. ``###### Title`` at line start.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class TreeBuilder:
    """
    Builds a :class:`TreeIndex` for one document.

    Args:
        llm: Object exposing ``async chat(messages, **kwargs) -> str``
            (the runtime ``LLM`` class). Used for the summary pass.
        settings: The ``knowledge.tree`` settings dict (missing keys take
            :data:`DEFAULT_TREE_SETTINGS` defaults).
    """

    def __init__(self, llm: Any, settings: Optional[Dict[str, Any]] = None):
        self.llm = llm
        merged = dict(DEFAULT_TREE_SETTINGS)
        merged.update(settings or {})
        self.max_depth = int(merged["max_depth"])
        self.max_tokens_per_node = int(merged["max_tokens_per_node"])

    async def build(self, text: str, document_name: str) -> TreeIndex:
        """
        Build the tree index for ``text``.

        Raises:
            TreeBuildError: When the document is empty or the LLM summary
                pass fails after a retry.
        """
        if not text or not text.strip():
            raise TreeBuildError(f"Document '{document_name}' has no extractable text")

        token_count = count_tokens(text)

        # Pass 1: deterministic structure (headings, else fixed windows).
        sections = self._segment(text)

        # Assemble tree skeleton with pre-order node ids and the KV mapping.
        kv: Dict[str, str] = {}
        counter = [0]

        def _next_id() -> str:
            node_id = f"{counter[0]:04d}"
            counter[0] += 1
            return node_id

        root = TreeNode(
            node_id=_next_id(),
            title=document_name,
            start_index=0,
            end_index=len(text),
        )
        # Root raw = preamble before the first section (often intro text).
        first_start = sections[0].start if sections else len(text)
        kv[root.node_id] = text[:first_start].strip()

        def _attach(section: _Section, parent: TreeNode) -> None:
            node = TreeNode(
                node_id=_next_id(),
                title=section.title,
                start_index=section.start,
                end_index=section.end,
            )
            parent.sub_nodes.append(node)
            if section.children:
                # Parent raw = intro text before its first child (keeps the
                # KV non-duplicative: descendants own their spans).
                intro_end = section.children[0].start
                kv[node.node_id] = text[section.start : intro_end].strip()
                for child in section.children:
                    _attach(child, node)
            else:
                kv[node.node_id] = text[section.start : section.end].strip()

        for section in sections:
            _attach(section, root)

        tree = TreeIndex(document=document_name, root=root, token_count=token_count, kv=kv)

        # Pass 2: LLM summaries (navigation-oriented, per node).
        await self._summarize(tree)

        tree.tree_token_count = count_tokens(tree.compressed_json())
        return tree

    # ------------------------------------------------------------------
    # Pass 1: deterministic segmentation
    # ------------------------------------------------------------------

    def _segment(self, text: str) -> List[_Section]:
        """Segment ``text`` into a section hierarchy (headings or windows)."""
        headings = list(_HEADING_RE.finditer(text))
        if len(headings) >= 2:
            sections = self._segment_by_headings(text, headings)
        else:
            sections = self._segment_by_windows(text, 0, len(text), title_prefix="Section")
        # Enforce the per-node token cap on leaves.
        for section in sections:
            self._split_oversized(text, section)
        return sections

    def _segment_by_headings(self, text: str, headings: List[re.Match]) -> List[_Section]:
        """Build a nested section list from ATX headings, capped at max_depth."""
        # Normalize heading levels: the shallowest heading level becomes 1.
        min_level = min(len(m.group(1)) for m in headings)
        flat: List[_Section] = []
        for i, match in enumerate(headings):
            depth = len(match.group(1)) - min_level + 1
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            flat.append(
                _Section(
                    title=match.group(2).strip(),
                    level=min(depth, self.max_depth),
                    start=match.start(),
                    end=end,
                )
            )

        # Fold the flat list into a hierarchy using a level stack.
        top: List[_Section] = []
        stack: List[_Section] = []
        for section in flat:
            while stack and stack[-1].level >= section.level:
                stack.pop()
            if stack:
                parent = stack[-1]
                parent.children.append(section)
                parent.end = max(parent.end, section.end)
                for ancestor in stack[:-1]:
                    ancestor.end = max(ancestor.end, section.end)
            else:
                top.append(section)
            stack.append(section)
        return top

    def _segment_by_windows(
        self, text: str, start: int, end: int, title_prefix: str
    ) -> List[_Section]:
        """Fixed token-window "pages" for unstructured text spans."""
        window_chars = max(1, self.max_tokens_per_node * _CHARS_PER_TOKEN)
        sections: List[_Section] = []
        pos = start
        part = 1
        while pos < end:
            window_end = min(pos + window_chars, end)
            if window_end < end:
                # Prefer breaking on a paragraph boundary inside the window.
                break_at = text.rfind("\n\n", pos + window_chars // 2, window_end)
                if break_at > pos:
                    window_end = break_at
            sections.append(
                _Section(
                    title=f"{title_prefix} {part}",
                    level=0,
                    start=pos,
                    end=window_end,
                )
            )
            pos = window_end
            part += 1
        return sections

    def _split_oversized(self, text: str, section: _Section) -> None:
        """Recursively split leaves whose span exceeds max_tokens_per_node."""
        if section.children:
            for child in section.children:
                self._split_oversized(text, child)
            return
        span_chars = section.end - section.start
        if span_chars <= self.max_tokens_per_node * _CHARS_PER_TOKEN:
            return
        section.children = self._segment_by_windows(
            text, section.start, section.end, title_prefix=f"{section.title} - Part"
        )

    # ------------------------------------------------------------------
    # Pass 2: LLM summaries
    # ------------------------------------------------------------------

    async def _summarize(self, tree: TreeIndex) -> None:
        """Fill node summaries via batched LLM calls (raises TreeBuildError)."""
        nodes = list(tree.walk())
        for batch_start in range(0, len(nodes), _SUMMARY_BATCH_SIZE):
            batch = nodes[batch_start : batch_start + _SUMMARY_BATCH_SIZE]
            summaries = await self._summarize_batch(tree, batch)
            for node in batch:
                node.summary = summaries.get(node.node_id, "").strip()[:400]

    async def _summarize_batch(self, tree: TreeIndex, nodes: List[TreeNode]) -> Dict[str, str]:
        """One LLM call: node excerpts in, ``{node_id: summary}`` out."""
        lines = []
        for node in nodes:
            excerpt = tree.fetch_raw(node.node_id)[:_EXCERPT_CHARS].replace("\n", " ")
            lines.append(f"- node_id: {node.node_id} | title: {node.title} | excerpt: {excerpt}")

        system = (
            "You build navigation summaries for a hierarchical document index. "
            "For each listed node, write one dense sentence (max 30 words) describing "
            "what information that section contains, so a retrieval system can decide "
            "whether the section answers a query. Include the concrete identifiers "
            "that appear in the excerpt - part names, codes, numeric values, "
            "intervals - verbatim; these are what the navigator matches queries "
            "against. Respond ONLY with a JSON object of the form "
            '{"summaries": {"<node_id>": "<summary>", ...}} covering every listed '
            "node_id. No markdown, no extra keys."
        )
        user = f"Document: {tree.document}\nNodes:\n" + "\n".join(lines)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        last_error: Optional[Exception] = None
        for attempt in range(2):  # one retry on transient/parse failure
            if attempt:
                # Short backoff before the retry so transient failures
                # (429 rate limits, provider hiccups) have a chance to
                # clear instead of retrying instantly into the same error.
                await asyncio.sleep(1 * (attempt + 1))
            try:
                # Notes:
                # - temperature 0.1 rather than 0.0: LLM.chat coerces falsy
                #   temperatures to the instance default (0.7).
                # - caching=False: summary batches for different documents
                #   (or rebuilt content) look "similar" to the semantic
                #   response cache; a stale hit would silently attach the
                #   wrong summaries to a fresh tree. Builds are already
                #   deduplicated by the MD5-keyed TreeCache.
                # - explicit max_tokens: a formation-level ``llm.settings.
                #   max_tokens`` chat cap would truncate the batch-summary
                #   JSON mid-object (up to 40 summaries per response) and
                #   fail the build; ~75 tokens per node covers a 30-word
                #   summary plus JSON overhead.
                response = await self.llm.chat(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=_SUMMARY_BATCH_SIZE * 75,
                    caching=False,
                    metadata={"component": "knowledge_tree_builder"},
                )
                parsed = extract_json_object(response)
                summaries = parsed.get("summaries")
                if not isinstance(summaries, dict):
                    raise TreeBuildError("Summary response missing 'summaries' object")
                return {str(k): str(v) for k, v in summaries.items()}
            except Exception as e:  # noqa: BLE001 - single retry, then re-raise
                last_error = e
        raise TreeBuildError(
            f"Tree summary generation failed for '{tree.document}': {last_error}"
        ) from last_error


def extract_json_object(response: str) -> Dict[str, Any]:
    """
    Extract the first JSON object from an LLM response.

    Tolerates markdown code fences and prose around the object. Raises
    ``TreeBuildError`` when no parseable object is found.
    """
    if not isinstance(response, str) or not response.strip():
        raise TreeBuildError("Empty LLM response")
    candidate = response.strip()
    # Strip a markdown code fence when present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise TreeBuildError("No JSON object found in LLM response")
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except Exception as e:
        raise TreeBuildError(f"Malformed JSON in LLM response: {e}") from e
    if not isinstance(parsed, dict):
        raise TreeBuildError("LLM response JSON is not an object")
    return parsed


def load_document_text(file_path: str, knowledge_source: Any = None) -> str:
    """
    Load a document's extractable text for token counting / tree building.

    Reuses the knowledge source's loader (markitdown-aware) when available so
    PDFs and office documents produce the same text the vector pipeline sees;
    falls back to a plain UTF-8 read.
    """
    loader = getattr(knowledge_source, "_load_file_content", None)
    if callable(loader):
        return loader(file_path)
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""
