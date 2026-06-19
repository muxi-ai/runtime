"""
Presidio-backed entity detector for names, addresses, orgs, DOB, and financial
identifiers.

Presidio is a core dependency and entity redaction is on by default (toggle via
``logging.redaction.entities``). The factory and detector still degrade
gracefully to regex-only if the NLP stack is somehow unavailable at runtime,
mirroring how document chunking treats the same spaCy model.
"""

import importlib.util
import logging
import threading
from typing import List, Optional, Sequence

from .base import EntityDetector, Span

logger = logging.getLogger(__name__)

# Model choice: small English model (~12MB), already required by document
# chunking. Accepts weaker PERSON/ORG recall than en_core_web_lg in exchange for
# a small footprint. Internal constant so a future upgrade is a one-line change.
_DEFAULT_MODEL = "en_core_web_sm"
_DEFAULT_MAX_CHARS = 4000

# Presidio entity types we request, mapped to our masking labels.
_LABEL_MAP = {
    "PERSON": "PERSON",
    "LOCATION": "ADDRESS",
    "ORGANIZATION": "ORG",
    "IBAN_CODE": "FINANCIAL",
    "US_BANK_NUMBER": "FINANCIAL",
    "CRYPTO": "FINANCIAL",
    "CREDIT_CARD": "FINANCIAL",
}
_REQUESTED_ENTITIES = list(_LABEL_MAP.keys()) + ["DATE_TIME"]
_DOB_CONTEXT = ("born", "dob", "date of birth", "birthday", "birth date")

_warned_missing = False


class PresidioDetector(EntityDetector):
    """Detects entities via a lazily-loaded, process-wide Presidio analyzer."""

    # Analyzers are cached per (languages, model) so distinct configurations get
    # distinct engines instead of silently reusing whichever was built first.
    _analyzers: dict = {}
    _analyzer_lock = threading.Lock()

    def __init__(
        self,
        languages: Sequence[str] = ("en",),
        model: str = _DEFAULT_MODEL,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ):
        self._languages = tuple(languages)
        self._model = model
        self._max_chars = max_chars

    @classmethod
    def _get_analyzer(cls, languages: Sequence[str], model: str):
        key = (frozenset(languages), model)
        analyzer = cls._analyzers.get(key)
        if analyzer is None:
            with cls._analyzer_lock:
                analyzer = cls._analyzers.get(key)
                if analyzer is None:
                    from presidio_analyzer import AnalyzerEngine
                    from presidio_analyzer.nlp_engine import NlpEngineProvider

                    provider = NlpEngineProvider(
                        nlp_configuration={
                            "nlp_engine_name": "spacy",
                            "models": [
                                {"lang_code": lang, "model_name": model} for lang in languages
                            ],
                        }
                    )
                    analyzer = AnalyzerEngine(
                        nlp_engine=provider.create_engine(),
                        supported_languages=list(languages),
                    )
                    cls._analyzers[key] = analyzer
        return analyzer

    def detect(self, text: str, language: str = "en") -> List[Span]:
        if not text:
            return []
        if len(text) > self._max_chars:
            logger.debug(
                "Entity detection skipped: text length %d exceeds max_chars=%d",
                len(text),
                self._max_chars,
            )
            return []
        try:
            analyzer = self._get_analyzer(self._languages, self._model)
            results = analyzer.analyze(text=text, language=language, entities=_REQUESTED_ENTITIES)
        except Exception:
            # Never let detection failures break the logging path.
            logger.debug("Entity detection failed; falling back to regex-only", exc_info=True)
            return []

        spans: List[Span] = []
        for r in results:
            label = self._map_label(r.entity_type, text, r.start)
            if label:
                spans.append(Span(r.start, r.end, label, r.score))
        return spans

    @staticmethod
    def _map_label(entity_type: str, text: str, start: int) -> Optional[str]:
        if entity_type == "DATE_TIME":
            # Only treat dates as DOB when birth context precedes them; otherwise
            # leave generic timestamps untouched.
            context = text[max(0, start - 30) : start].casefold()
            if any(keyword in context for keyword in _DOB_CONTEXT):
                return "DOB"
            return None
        return _LABEL_MAP.get(entity_type)


def build_entity_detector(enabled: bool = True) -> Optional[EntityDetector]:
    """
    Build the entity detector when enabled.

    Returns None (regex-only) when disabled via logging.redaction.entities, or
    when the presidio NLP stack is unexpectedly unavailable (it is a core
    dependency) — logging a one-time warning in the latter case so the
    degradation is visible.
    """
    global _warned_missing
    if not enabled:
        return None
    if importlib.util.find_spec("presidio_analyzer") is None:
        if not _warned_missing:
            logger.warning(
                "Entity redaction is enabled but 'presidio-analyzer' is unavailable; "
                "falling back to regex-only redaction. This is unexpected since presidio "
                "is a core dependency - check the installation."
            )
            _warned_missing = True
        return None
    return PresidioDetector()
