# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        The Tuner - Detection, Distillation, MUXI.md Curation
# Description:  Prompt builder/parser for the tuning loop's tune step
# Role:         Turns the digest pass into MUXI.md revisions + learnings
# Usage:        Driven by TuningService.run_once after the digest step
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, "The loop" step 2. The tuner reads the
# fresh digest, recent formation-log entries, and its experiment
# memories; detects patterns worth acting on (cost hotspots, misrouted
# request classes, flaky tools, model over-provisioning); and distills
# behavioral learnings into a candidate MUXI.md revision. It never
# touches formation config -- config changes are human deployments,
# surfaced only as prose recommendations.
#
# Mirrors the FormationLogSummarizer contract: the caller drives the LLM
# call (build_prompt -> generate_text -> parse_response); every failure
# parses down to None so the tuning loop is never broken by the tuner.
# =============================================================================

from typing import Any, Dict, List, Optional

from ...utils.fastjson import json

# Bounds on what one pass may propose; curation is rewriting, not
# accretion, so a run never needs more than a handful of changes.
MAX_LEARNINGS_PER_RUN = 5
MAX_RECOMMENDATIONS_PER_RUN = 5
MAX_LEARNING_CHARS = 500
MAX_EVIDENCE_CHARS = 500
MAX_RECOMMENDATION_CHARS = 500


class TunerStep:
    """Builds and parses the tune-step LLM call."""

    def build_prompt(
        self,
        activity_report: str,
        current_muxi_md: Optional[str],
        formation_log_block: Optional[str],
        active_learnings: List[Dict[str, Any]],
        retired_learnings: List[Dict[str, Any]],
        dismissed_learnings: List[str],
        metric_keys: List[str],
        max_bytes: int,
    ) -> str:
        parts: List[str] = [
            "You are the tuner of an AI formation: you curate MUXI.md, the "
            "formation's file of behavioral learnings. MUXI.md steers dynamic "
            "per-turn decisions (routing, model choice within the shipped "
            "hierarchy, tool selection, clarification thresholds). It is "
            "injected into every turn's context, so it must stay concise, "
            "operational, and general.\n",
            "Detect patterns worth acting on in the activity below: cost "
            "hotspots, misrouted request classes, flaky tools, model "
            "over-provisioning. Distill them into learnings and produce a "
            "revised MUXI.md.\n",
            "RULES:\n"
            "- Base every learning ONLY on the activity report and log entries "
            "below. Do not invent patterns.\n"
            "- CURATE, never append: rewrite sections, merge overlapping "
            "guidance, retire stale learnings. The revised file MUST stay "
            f"under {max_bytes} bytes.\n"
            "- NEVER suggest configuration or yaml changes inside MUXI.md; "
            "anything requiring a deployment (yaml edits, plan upgrades, new "
            "tools) goes into 'recommendations' as prose for a human.\n"
            "- HARD PRIVACY RULE: MUXI.md is injected into every user's "
            "context. NEVER include user identifiers, user names, prompt or "
            "message content, or any user-derived specifics.\n"
            "- BE SPECIFIC about operations: name the exact tools, models, "
            "event types, and time windows involved ('the jira MCP', not "
            "'some tools'). Operational specifics are the point; only "
            "user-derived specifics are banned.\n"
            "- Each learning is one imperative sentence of operational "
            "guidance (e.g. 'Back off the jira MCP during 14:00-16:00 UTC "
            "rate-limit windows.').\n"
            "- When a learning targets a measurable problem, set its "
            "'metric_key' to one of the observed metric keys listed below so "
            "later runs can verify the metric moved; use null otherwise.\n"
            "- Propose at most "
            f"{MAX_LEARNINGS_PER_RUN} learnings; an empty list is a fine "
            "answer when nothing stands out. Do not re-propose dismissed or "
            "retired learnings.",
        ]

        parts.append(f"\nCurrent MUXI.md:\n{current_muxi_md or '(the file does not exist yet)'}")

        if formation_log_block:
            parts.append(f"\nRecent formation log entries:\n{formation_log_block}")

        if active_learnings:
            lines = [
                f"- {record.get('learning')} (watching {record.get('metric_key') or 'nothing'})"
                for record in active_learnings
            ]
            parts.append(
                "\nLearnings currently under observation (keep them):\n" + "\n".join(lines)
            )

        if retired_learnings:
            lines = [f"- {record.get('learning')}" for record in retired_learnings]
            parts.append(
                "\nRetired learnings -- their watched metric did not move; the "
                "revised MUXI.md MUST NOT contain them:\n" + "\n".join(lines)
            )

        if dismissed_learnings:
            lines = [f"- {learning}" for learning in dismissed_learnings]
            parts.append(
                "\nDismissed learnings -- the operator rejected these; NEVER "
                "re-propose them:\n" + "\n".join(lines)
            )

        if metric_keys:
            parts.append("\nObserved metric keys:\n" + "\n".join(f"- {key}" for key in metric_keys))

        parts.append(
            "\nRespond with a JSON object in exactly this structure:\n"
            "{\n"
            '  "muxi_md": "the full revised MUXI.md content, or an empty string '
            'when nothing should change",\n'
            '  "learnings": [{"learning": "...", "evidence": "...", '
            '"metric_key": "... or null"}],\n'
            '  "recommendations": ["prose recommendation for a human '
            'deployment"]\n'
            "}\n"
        )
        parts.append(f"\nAggregated activity report:\n{activity_report}\n")
        return "\n".join(parts)

    def parse_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM response; None means the tuner skips this run."""
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

        muxi_md = payload.get("muxi_md")
        muxi_md = muxi_md.strip() if isinstance(muxi_md, str) and muxi_md.strip() else None

        learnings: List[Dict[str, Optional[str]]] = []
        for item in payload.get("learnings") or []:
            if not isinstance(item, dict):
                continue
            learning = item.get("learning")
            if not isinstance(learning, str) or not learning.strip():
                continue
            evidence = item.get("evidence")
            metric_key = item.get("metric_key")
            learnings.append(
                {
                    "learning": learning.strip()[:MAX_LEARNING_CHARS],
                    "evidence": (
                        evidence.strip()[:MAX_EVIDENCE_CHARS]
                        if isinstance(evidence, str) and evidence.strip()
                        else ""
                    ),
                    "metric_key": (
                        metric_key.strip()
                        if isinstance(metric_key, str) and metric_key.strip()
                        else None
                    ),
                }
            )
            if len(learnings) >= MAX_LEARNINGS_PER_RUN:
                break

        recommendations: List[str] = []
        for item in payload.get("recommendations") or []:
            if isinstance(item, str) and item.strip():
                recommendations.append(item.strip()[:MAX_RECOMMENDATION_CHARS])
            if len(recommendations) >= MAX_RECOMMENDATIONS_PER_RUN:
                break

        return {"muxi_md": muxi_md, "learnings": learnings, "recommendations": recommendations}


__all__ = ["MAX_LEARNINGS_PER_RUN", "TunerStep"]
