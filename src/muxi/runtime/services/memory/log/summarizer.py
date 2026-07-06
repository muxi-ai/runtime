# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Captain's Log Summarizer - Narrative Digest Generation
# Description:  LLM-based summarization of conversation batches into log entries
# Role:         Turns recent turns into structured narrative sections + lessons
# Usage:        Used by CaptainsLogService's periodic summarization job
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 2 (Captain's Log). One digest call per user per run
# produces the PRD's structured sections (summary, decisions, projects,
# context) plus the lessons-learned list. The same response also carries
# entities/relationships for the knowledge graph integration -- the graph
# side is parsed and validated by the Phase 1 KnowledgeGraphExtractor, so
# one LLM call feeds both layers.
#
# Mirrors the Phase 1 extractor contract: the model is resolved by the
# caller, caching is disabled (similar prompts for different conversations
# must not return stale digests), and every failure parses down to None --
# summarization must never break the background loop.
# =============================================================================

from typing import Any, Dict, List, Optional

from ....utils.fastjson import json


class CaptainsLogSummarizer:
    """Summarizes conversation batches into structured log entry sections.

    The caller drives the LLM call itself (build_prompt -> generate_text ->
    parse_response) because the raw response is also handed to the Phase 1
    KnowledgeGraphExtractor parser for the entities/relationships fields.
    """

    def build_prompt(
        self,
        conversation: str,
        entry_date: str,
        previous_entry: Optional[Dict[str, Any]] = None,
        extract_lessons: bool = True,
    ) -> str:
        """Build the digest prompt for the LLM."""
        parts: List[str] = [
            f"You are writing the captain's log entry for {entry_date}: a concise narrative "
            "record of what happened in the user's recent conversations.\n",
            "Capture: decisions made and their rationale, projects discussed and status "
            "changes, notable context shifts, and action items or outcomes.\n",
            "RULES:\n"
            "- Base the entry ONLY on the conversation below. Do not invent events.\n"
            "- Write in the past tense, third person, referring to the user as 'the user'.\n"
            "- DO NOT include sensitive information (passwords, credit cards, government "
            "IDs, financial or medical details).\n"
            "- Keep the summary under 100 words; decisions and projects are short phrases.\n"
            "- Use empty strings/arrays for sections with nothing to record.",
        ]

        if previous_entry is not None:
            existing = {
                "summary": previous_entry.get("summary") or "",
                "decisions": previous_entry.get("decisions") or [],
                "projects": previous_entry.get("projects") or [],
                "context": previous_entry.get("context") or "",
            }
            parts.append(
                "\nAn entry for this date already exists. Merge the new conversation into "
                "it, keeping everything still accurate:\n"
                f"{json.dumps(existing)}"
            )

        if extract_lessons:
            parts.append(
                "\nIn addition, extract any LESSONS LEARNED as a separate list of "
                '{"rule", "context"} items. Lessons are reusable, prescriptive rules of '
                "thumb the assistant should apply in future sessions (e.g. tool or "
                "phrasing choices that worked or failed) -- NOT facts about the user and "
                "NOT one-off events. Return an empty list when there are none."
            )

        parts.append(
            "\nAlso extract knowledge graph facts the user explicitly stated about "
            "themselves and their world, as entities and relationships (same rules: no "
            "questions, no hypotheticals, no sensitive data). Refer to the user as the "
            'entity named "User" (type "person"). Assign each item a confidence between '
            "0.0 and 1.0. Return empty arrays when there is nothing to extract."
        )

        lessons_line = (
            '  "lessons": [{"rule": "...", "context": "..."}],\n' if extract_lessons else ""
        )
        parts.append(
            "\nRespond with a JSON object in exactly this structure:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "decisions": ["..."],\n'
            '  "projects": ["..."],\n'
            '  "context": "...",\n'
            f"{lessons_line}"
            '  "entities": [{"name": "...", "type": "...", "attributes": {}, '
            '"confidence": 0.9}],\n'
            '  "relationships": [{"from": "User", "from_type": "person", "to": "...", '
            '"to_type": "...", "type": "...", "confidence": 0.9}]\n'
            "}\n"
        )

        parts.append(f"\nConversation:\n{conversation}\n")
        return "\n".join(parts)

    def parse_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse the LLM response into validated digest sections.

        Tolerates fenced code blocks and drops malformed items instead of
        raising. Returns None when the response is not a JSON object (the
        caller skips the run). The raw response should additionally be fed
        to KnowledgeGraphExtractor.parse_response for the graph fields.
        """
        if not response or not isinstance(response, str):
            return None

        clean = response.strip()
        if clean.startswith("```"):
            first_newline = clean.find("\n")
            if first_newline > 0:
                clean = clean[first_newline + 1 :]
            if clean.endswith("```"):
                clean = clean[:-3].strip()

        try:
            payload = json.loads(clean)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None

        return {
            "summary": _as_text(payload.get("summary")),
            "decisions": _as_text_list(payload.get("decisions")),
            "projects": _as_text_list(payload.get("projects")),
            "context": _as_text(payload.get("context")),
            "lessons": _as_lessons(payload.get("lessons")),
        }


def _as_text(value: Any) -> Optional[str]:
    """Coerce a section value to stripped text, or None when empty."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _as_text_list(value: Any) -> List[str]:
    """Coerce a section value to a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return items


def _as_lessons(value: Any) -> List[Dict[str, Optional[str]]]:
    """Validate raw lesson items down to {rule, context} dicts."""
    if not isinstance(value, list):
        return []
    lessons = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule")
        if not isinstance(rule, str) or not rule.strip():
            continue
        context = item.get("context")
        lessons.append(
            {
                "rule": rule.strip(),
                "context": (
                    context.strip() if isinstance(context, str) and context.strip() else None
                ),
            }
        )
    return lessons
