# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Formation Captain's Log - Digest Prompt and Privacy Lint
# Description:  Formation-scope narrative digest of the event spool
# Role:         Prompt builder/parser + sentence-level privacy gate
# Usage:        Driven by CaptainsLogService.digest_formation (tuning loop)
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, part 2 step 1 (Formation Captain's Log).
# Same storage and date-grain as the per-user log, written under the
# reserved formation user id. Formation scope is visible to every user,
# so the privacy rule is hard: no user ids, no prompt content, no
# user-derived specifics. The privacy lint runs on every write; a
# rejection drops the offending sentence, never the digest.
# =============================================================================

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ....utils.fastjson import json
from ....utils.redaction import DEFAULT_ENTITY_THRESHOLD, get_entity_detector
from ....utils.sensitive_terms import SENSITIVE_KEY_TERMS

# Reserved user id scoping formation-wide log entries. Not a real user:
# "0" is the single-user-mode user, so the sentinel must be distinct and
# impossible as an external id (external ids are lowercased; this one is
# also excluded from per-user enumeration paths such as the memory lint).
FORMATION_LOG_USER_ID = "__formation__"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Card-length digit runs, tolerant of space/hyphen group separators
# ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111").
_LONG_DIGIT_RUN = re.compile(r"(?:\d[ -]?){14,}\d")

# Entity-detector labels that make a sentence user-derived. ORG and
# DATE_TIME are deliberately NOT here: tool/vendor names and time windows
# are the operational content the formation log exists to record
# ("Jira rate-limits 14:00-16:00" must survive the lint).
_PRIVATE_ENTITY_LABELS = {"PERSON", "ADDRESS", "FINANCIAL"}


class FormationLogSummarizer:
    """Builds and parses the formation-scope digest LLM call.

    Mirrors CaptainsLogSummarizer's contract: the caller drives the LLM
    call (build_prompt -> generate_text -> parse_response); every failure
    parses down to None so the tuning loop is never broken by a digest.
    """

    def build_prompt(
        self,
        activity_report: str,
        entry_date: str,
        previous_entry: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the formation digest prompt from the aggregated report."""
        parts: List[str] = [
            f"You are writing the formation's operations log entry for {entry_date}: a "
            "concise operational narrative of how this AI formation performed, written "
            "for the formation itself to learn from.\n",
            "Capture: traffic shape, tool-failure clusters, routing anomalies, cost "
            "hotspots, and incidents. Focus on operational patterns, not individual "
            "conversations.\n",
            "RULES:\n"
            "- Base the entry ONLY on the aggregated activity report below. Do not "
            "invent events.\n"
            "- HARD PRIVACY RULE: this entry is visible to every user of the "
            "formation. NEVER include user identifiers, user names, prompt or message "
            "content, or any user-derived specifics. Generalize: 'a spike of "
            "FAQ-class requests', never 'user X asked about Y'.\n"
            "- Write in the past tense. Keep the summary under 120 words.\n"
            "- Use empty strings for sections with nothing to record.",
        ]

        if previous_entry is not None:
            existing = {
                "summary": previous_entry.get("summary") or "",
                "context": previous_entry.get("context") or "",
            }
            parts.append(
                "\nAn entry for this date already exists. Merge the new activity into "
                "it, keeping everything still accurate:\n"
                f"{json.dumps(existing)}"
            )

        parts.append(
            "\nRespond with a JSON object in exactly this structure:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "context": "..."\n'
            "}\n"
        )
        parts.append(f"\nAggregated activity report:\n{activity_report}\n")
        return "\n".join(parts)

    def parse_response(self, response: str) -> Optional[Dict[str, Optional[str]]]:
        """Parse the LLM response; None means the caller skips the run."""
        if not response or not isinstance(response, str):
            return None
        clean = response.strip()
        if clean.startswith("```"):
            first_newline = clean.find("\n")
            if first_newline > 0:
                clean = clean[first_newline + 1 :]  # noqa: E203
            if clean.endswith("```"):
                clean = clean[:-3].strip()
        try:
            payload = json.loads(clean)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        summary = payload.get("summary")
        context = payload.get("context")
        summary = summary.strip() if isinstance(summary, str) and summary.strip() else None
        context = context.strip() if isinstance(context, str) and context.strip() else None
        if summary is None:
            return None
        return {"summary": summary, "context": context}


def lint_formation_digest(
    text: Optional[str], known_user_ids: Iterable[str]
) -> Tuple[Optional[str], int]:
    """Sentence-level privacy gate for formation-scope digest text.

    Drops every sentence that carries a known user id, an email address,
    an SSN/card-length digit run, a sensitive keyword, or (when the
    entity detector is enabled) a detected personal entity. Returns the
    cleaned text and the number of dropped sentences -- never rejects the
    whole digest.
    """
    if not text:
        return text, 0

    user_id_needles = [
        user_id.lower()
        for user_id in known_user_ids
        # Very short ids ("0" in single-user mode) would match everywhere;
        # the digest report never carries them verbatim anyway.
        if isinstance(user_id, str) and len(user_id) >= 3
    ]

    detector = get_entity_detector()
    kept: List[str] = []
    dropped = 0
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence.strip():
            continue
        if _is_private_sentence(sentence, user_id_needles, detector):
            dropped += 1
            continue
        kept.append(sentence.strip())

    cleaned = " ".join(kept)
    return (cleaned if cleaned else None), dropped


def lint_formation_lines(
    text: Optional[str], known_user_ids: Iterable[str]
) -> Tuple[Optional[str], int]:
    """Line-level privacy gate for markdown destined for every user.

    Same predicates as :func:`lint_formation_digest` but drops whole
    lines instead of joining sentences, preserving markdown structure
    (the tuner's MUXI.md revisions are markdown, not prose). Returns the
    cleaned text and the number of dropped lines.
    """
    if not text:
        return text, 0

    user_id_needles = [
        user_id.lower()
        for user_id in known_user_ids
        if isinstance(user_id, str) and len(user_id) >= 3
    ]

    detector = get_entity_detector()
    kept: List[str] = []
    dropped = 0
    for line in text.splitlines():
        if line.strip() and _is_private_sentence(line, user_id_needles, detector):
            dropped += 1
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    return (cleaned if cleaned else None), dropped


def _is_private_sentence(sentence: str, user_id_needles: List[str], detector) -> bool:
    lowered = sentence.lower()
    if any(needle in lowered for needle in user_id_needles):
        return True
    if _EMAIL_PATTERN.search(sentence) or _SSN_PATTERN.search(sentence):
        return True
    if any(term in lowered for term in SENSITIVE_KEY_TERMS):
        return True
    if _LONG_DIGIT_RUN.search(sentence):
        return True
    if detector is not None:
        try:
            if any(
                span.score >= DEFAULT_ENTITY_THRESHOLD and span.label in _PRIVATE_ENTITY_LABELS
                for span in detector.detect(sentence)
            ):
                return True
        except Exception:
            # Fail closed: the formation log is visible to every user,
            # so an unverifiable sentence is never published.
            return True
    return False


__all__ = [
    "FORMATION_LOG_USER_ID",
    "FormationLogSummarizer",
    "lint_formation_digest",
    "lint_formation_lines",
]
