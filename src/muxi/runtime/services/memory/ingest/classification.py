# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Ingestion Content Triage - Prototype-Similarity Classification
# Description:  Tier 0/1 content-type triage for the memory ingestion pipeline
# Role:         Maps raw ingested content to a category + per-source noise gate
# Usage:        Used by MemoryIngestionService (services/memory/ingest/service.py)
# Author:       Muxi Framework Team
#
# Memory Ingestion Phase 3a, pipeline stage 1 (classify) + stage 2 (filter).
#
# Triage rides the shipped LocalClassifier prototype-similarity machinery
# (services/classification): one IntentSpec per content category whose
# positive set is that category's exemplars and whose negative set is the
# union of every other category's exemplars. classify_binary() returns a
# margin per category; the category with the largest margin wins. No
# frontier LLM is involved -- this is the PRD's "cheap local classifier"
# tier, ~5-30 ms per item on the cached ONNX encoder.
#
# The noise gate is aggressive by default (PRD: "80%+ of most data streams
# is noise"), tunable per source through the smallest viable config surface:
#
#   memory:
#     ingestion:
#       sources:
#         gmail:
#           filter: lenient   # strict | lenient | off
#
# Filtered items are NOT lost: the raw memory.ingested event is appended
# before the pipeline runs, and the filtered disposition is recorded as an
# ingestion.filtered event -- improved filters can replay exactly that set.
# =============================================================================

from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

from ...classification import IntentSpec

# ---------------------------------------------------------------------------
# Content categories (PRD "Processing Pipeline" stage 1)
# ---------------------------------------------------------------------------

CATEGORY_PERSONAL = "personal"
CATEGORY_WORK = "work"
CATEGORY_TRANSACTIONAL = "transactional"
CATEGORY_PROMOTIONAL = "promotional"
CATEGORY_AUTOMATED = "automated"

# Returned when classification itself fails (e.g. the local embedding
# model is unavailable). Unknown items are always kept -- triage failure
# must never lose developer data.
CATEGORY_UNKNOWN = "unknown"

# Prototype exemplars per category. Kept short (<100 chars) per the
# classification module's authoring guidelines; each category's negative
# set is built from the union of the other categories' exemplars.
CATEGORY_EXAMPLES: Dict[str, List[str]] = {
    CATEGORY_PERSONAL: [
        "Hey, are we still on for dinner at mom's place on Sunday?",
        "I moved to a new flat in Camden last week",
        "My daughter starts school in September",
        "Thanks for checking in, my knee is feeling much better",
        "I've been getting into bouldering lately, we should go together",
        "Can't wait to see you at the wedding next month",
        "My favorite coffee place closed down, so sad",
        "I finally finished reading that book you recommended",
        "We adopted a rescue dog named Biscuit",
        "Happy birthday! Hope the new decade treats you well",
    ],
    CATEGORY_WORK: [
        "The staging deploy is blocked on the database migration review",
        "Meeting notes: we agreed to ship the beta on the 15th",
        "Can you review my PR for the auth refactor before standup?",
        "Q3 roadmap draft attached, comments welcome until Friday",
        "The client asked to move the demo to Thursday afternoon",
        "Sprint retro action items: reduce flaky tests, document runbooks",
        "I'm presenting the architecture proposal at the all-hands",
        "New hire onboarding checklist updated with security training",
        "The incident postmortem is scheduled for tomorrow at 10",
        "Budget approval for the new vendor came through",
    ],
    CATEGORY_TRANSACTIONAL: [
        "Your order #4521 has shipped and will arrive on Tuesday",
        "Receipt: $42.17 paid to Cloud Hosting Inc on 2026-05-01",
        "Your subscription renewal was successful, next billing June 3",
        "Payment confirmation: invoice INV-2210 settled in full",
        "Your table booking for 4 at 7pm is confirmed",
        "Boarding pass attached for flight BA117 on Friday",
        "Your package was delivered to the front porch",
        "Direct debit of $89.00 to City Power scheduled for the 28th",
        "Your return has been processed, refund in 3-5 business days",
        "Appointment confirmed: dental checkup on March 12 at 9am",
    ],
    CATEGORY_PROMOTIONAL: [
        "FLASH SALE: 50% off everything this weekend only!",
        "Don't miss our summer collection, shop the new arrivals now",
        "Upgrade to premium today and get your first month free",
        "You've been selected for an exclusive members-only discount",
        "Last chance: earn double points on all purchases this week",
        "Our biggest deal of the year ends at midnight",
        "New in: the gadgets everyone is talking about",
        "Subscribe to our newsletter for weekly inspiration",
        "Refer a friend and you both get $20 credit",
        "Black Friday preview: doorbusters start Thursday",
    ],
    CATEGORY_AUTOMATED: [
        "Nightly backup completed successfully with 0 warnings",
        "ALERT: CPU usage above 90% on host web-03 for 15 minutes",
        "Your password was changed. If this wasn't you, contact support",
        "Build #8841 passed on branch main in 6m12s",
        "Someone logged in to your account from a new device",
        "Weekly usage report: 1,204 API calls, 3 errors",
        "Your certificate for example.com expires in 14 days",
        "Cron job daily-sync exited with status 0",
        "New sign-in to your account from Chrome on Windows",
        "Disk space warning: /var is 92% full on db-01",
    ],
}

CONTENT_CATEGORIES: Tuple[str, ...] = tuple(CATEGORY_EXAMPLES)

# Registration key prefix on the shared LocalClassifier instance. The
# ingestion specs are registered lazily by the ingestion service (not part
# of the classifier's built-in warmup set) so formations that never ingest
# don't pay the prototype-embedding cost.
INTENT_PREFIX = "ingest_"


def build_category_specs() -> Dict[str, IntentSpec]:
    """Build one binary IntentSpec per content category.

    Positive = the category's exemplars; negative = the union of every
    other category's exemplars. classify_binary()'s margin then measures
    "closer to this category than to the rest", and the arg-max margin
    across categories is the triage label.
    """
    specs: Dict[str, IntentSpec] = {}
    for category, positives in CATEGORY_EXAMPLES.items():
        negatives = [
            example
            for other, examples in CATEGORY_EXAMPLES.items()
            if other != category
            for example in examples
        ]
        specs[category] = IntentSpec(
            name=f"{INTENT_PREFIX}{category}",
            description=f"True when ingested content is {category} in nature",
            positive=list(positives),
            negative=negatives,
        )
    return specs


# Built once at import time: the specs are pure constants (frozen
# dataclasses over the exemplar lists above), so classify calls at
# ingestion scale reuse the same objects instead of reconstructing five
# specs with ~40-element negative sets per item.
CATEGORY_SPECS: Dict[str, IntentSpec] = build_category_specs()


async def classify_content(classifier, text: str) -> Tuple[str, float]:
    """Triage one content string into a category via prototype similarity.

    Registers the module-constant ingestion IntentSpecs on the shared
    classifier (idempotent -- registration is cached per process) and
    returns ``(category, margin)`` for the best-scoring category.

    Raises whatever the classifier raises (embedding backend failures);
    the ingestion service catches and fails open to CATEGORY_UNKNOWN.
    """
    for spec in CATEGORY_SPECS.values():
        await classifier.register(spec)

    best_category = CATEGORY_UNKNOWN
    best_margin = float("-inf")
    for category, spec in CATEGORY_SPECS.items():
        _, margin = await classifier.classify_binary(spec.name, text)
        if margin > best_margin:
            best_category = category
            best_margin = margin
    return best_category, best_margin


# ---------------------------------------------------------------------------
# Noise gate (PRD "Processing Pipeline" stage 2)
# ---------------------------------------------------------------------------

FILTER_STRICT = "strict"
FILTER_LENIENT = "lenient"
FILTER_OFF = "off"

FILTER_LEVELS: FrozenSet[str] = frozenset({FILTER_STRICT, FILTER_LENIENT, FILTER_OFF})

# The default is aggressive (PRD: "Filter is aggressive by default,
# tunable per source"): only personal and work content survives strict.
# Unknown-category items are always kept regardless of level.
DEFAULT_FILTER_LEVEL = FILTER_STRICT

FILTERED_CATEGORIES: Dict[str, FrozenSet[str]] = {
    FILTER_STRICT: frozenset({CATEGORY_PROMOTIONAL, CATEGORY_AUTOMATED, CATEGORY_TRANSACTIONAL}),
    FILTER_LENIENT: frozenset({CATEGORY_PROMOTIONAL}),
    FILTER_OFF: frozenset(),
}


def is_filtered(category: str, filter_level: str) -> bool:
    """Return True when the noise gate drops this category at this level."""
    return category in FILTERED_CATEGORIES.get(filter_level, frozenset())
