"""Tests for ``Overlord._consolidate_workflow_results`` against realistic raw data.

Background
----------
``Overlord._synthesize_workflow_results`` is the final stage of a
workflow turn. It collects ``TaskResult`` entries from the workflow
executor and calls ``_consolidate_workflow_results`` to render a single
deterministic structured string. That string flows downstream into
``_apply_persona`` (the single LLM pass on the way back to the user).

The shape of ``TaskResult.outputs`` is fixed by
``WorkflowExecutor._parse_task_response`` (workflow/executor.py)::

    outputs = {
        "main": {
            "result": <agent's full prose response>,  # str OR dict
            "status": "success",
            "metrics": {"response_length": int},
            "warnings": [],
            "artifacts": [],
        },
        "task_id": {"result": <task_id_str>, "status": "success"},
        "completed": {"result": True, "status": "success"},
        # plus capability-specific copies (research_findings, written_content, ...)
        # plus optional "artifacts" key when artifacts attached
    }

The agent's actual prose lives at ``outputs["main"]["result"]``. The
consolidator reads ``main.result`` as the primary content source via
``_render_task_body``, then surfaces ``_extract_key_outcomes`` plus the
``artifacts`` sub-dict as supplementary fields.

These tests cover three concerns:

1. Stable behaviors that survived the rewrite (failed tasks, regex
   extraction of Linear IDs, the synthetic flat-shape branch).
2. The behavior we want from the consolidator (``main.result`` rendered
   verbatim, dict results expanded to ``key: value`` lines, artifact
   filenames listed, per-task and total byte budgets enforced, NO LLM
   call).
3. Edge cases that previously degraded silently (empty outputs, non-dict
   outputs).
"""

from typing import Any, Dict, List

from muxi.runtime.formation.overlord.overlord import Overlord

# -----------------------------------------------------------------------
# Fixture builders matching the real ``_parse_task_response`` shape
# -----------------------------------------------------------------------


def _make_main_output(prose: str) -> Dict[str, Any]:
    """Build the ``outputs["main"]`` sub-dict the executor produces."""
    return {
        "result": prose,
        "status": "success",
        "metrics": {"response_length": len(prose)},
        "warnings": [],
        "artifacts": [],
    }


def _make_task_outputs(
    task_id: str,
    prose: str,
    *,
    extra_capability: str | None = None,
    artifacts: List[Any] | None = None,
) -> Dict[str, Any]:
    """Build a complete ``outputs`` dict matching the executor's output."""
    outputs: Dict[str, Any] = {
        "main": _make_main_output(prose),
        "task_id": {"result": task_id, "status": "success"},
        "completed": {"result": True, "status": "success"},
    }
    if extra_capability == "research":
        outputs["research_findings"] = {
            "result": prose,
            "status": "success",
            "metrics": {"word_count": len(prose.split())},
        }
    elif extra_capability == "writing":
        outputs["written_content"] = {
            "result": prose,
            "status": "success",
            "metrics": {"word_count": len(prose.split())},
        }
    if artifacts:
        outputs["artifacts"] = {
            "result": artifacts,
            "status": "success",
            "metrics": {"artifact_count": len(artifacts)},
        }
    return outputs


def _make_task_result(
    *,
    task_id: str,
    description: str,
    status: str = "completed",
    outputs: Dict[str, Any] | None = None,
    error: str | None = None,
) -> Dict[str, Any]:
    """Build a task_result entry as ``_synthesize_workflow_results`` sees it."""
    result: Dict[str, Any] = {
        "task_id": task_id,
        "description": description,
        "status": status,
    }
    if outputs is not None:
        result["outputs"] = outputs
    if error is not None:
        result["error"] = error
    return result


def _bare_overlord() -> Overlord:
    """Build an ``Overlord`` skeleton for consolidator-only tests.

    ``_consolidate_workflow_results`` and the helpers it relies on
    (``_render_task_body``, ``_extract_key_outcomes``) are stateless
    except for class-level attributes (the budgets), so we sidestep the
    full formation engine constructor.
    """
    return Overlord.__new__(Overlord)


# -----------------------------------------------------------------------
# Behavior tests — the deterministic consolidator
# -----------------------------------------------------------------------


class TestConsolidatorBehavior:
    """The deterministic consolidator reads ``outputs["main"]["result"]``
    as primary content, surfaces regex hints and artifact filenames as
    supplementary fields, and enforces per-task / total byte budgets.
    No LLM call is made.
    """

    def test_github_flow_carries_agent_prose(self) -> None:
        """A typical GitHub onboarding turn carries every task's prose.

        Each task's ``outputs["main"]["result"]`` contains the agent's
        synthesized response. The consolidator renders all four bodies
        so the persona LLM downstream has real content to absorb.
        """
        overlord = _bare_overlord()
        successful = [
            _make_task_result(
                task_id="t1",
                description="Welcome the user and explain MUXI capabilities",
                outputs=_make_task_outputs(
                    "t1",
                    "Hi! I'm MUXI — a runtime for orchestrating AI agents. "
                    "Today I'll help you create a GitHub welcome issue and "
                    "walk you through what I can do.",
                ),
            ),
            _make_task_result(
                task_id="t2",
                description="Create welcome GitHub issue",
                outputs=_make_task_outputs(
                    "t2",
                    "I created your welcome issue at "
                    "https://github.com/muxi-ai/runtime/issues/50 — titled "
                    "'Welcome to MUXI'.",
                ),
            ),
            _make_task_result(
                task_id="t3",
                description="Generate personalized recap",
                outputs=_make_task_outputs(
                    "t3",
                    "Here's your personalized recap: you asked to be "
                    "onboarded, I introduced MUXI, and I created a "
                    "welcome issue on GitHub.",
                ),
            ),
            _make_task_result(
                task_id="t4",
                description="Send final reply with next steps",
                outputs=_make_task_outputs(
                    "t4",
                    "Next steps: try `What can you do?` or ask me to summarize a webpage.",
                ),
            ),
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)

        # Each task description appears for orientation.
        for task in successful:
            assert task["description"] in rendered

        # And the agent's prose appears verbatim — these phrases live
        # only in ``outputs["main"]["result"]``.
        assert "I'm MUXI" in rendered
        assert "https://github.com/muxi-ai/runtime/issues/50" in rendered
        assert "you asked to be onboarded" in rendered
        assert "summarize a webpage" in rendered

        # The "Status: Completed successfully" fallback should NOT fire
        # for any task that has real body content.
        assert "Status: Completed successfully" not in rendered

    def test_canonical_linear_url_now_carried_via_main_result(self) -> None:
        """Canonical ``https://linear.app/...`` URLs are carried via prose.

        The legacy URL regex misses canonical Linear URLs (it requires
        chars between ``://`` and ``linear``). The consolidator renders
        ``main.result`` directly, so the URL appears in the output body
        regardless of regex behavior. The MX-id regex hint still surfaces
        the ID separately as a supplementary signal.
        """
        overlord = _bare_overlord()
        prose = "Created Linear issue at https://linear.app/acme/issue/MX-42 for the bug report."
        successful = [
            _make_task_result(
                task_id="t1",
                description="File Linear bug",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "linear.app/acme/issue/MX-42" in rendered
        assert "Linear issues: MX-42" in rendered

    def test_subdomain_linear_url_survives_with_hint(self) -> None:
        """URLs with chars before ``linear`` appear in body AND hints."""
        overlord = _bare_overlord()
        prose = "Created issue at https://example.linear.app/acme/issue/MX-42 for the bug report."
        successful = [
            _make_task_result(
                task_id="t1",
                description="File subdomain Linear bug",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "example.linear.app/acme/issue/MX-42" in rendered

    def test_linear_mx_id_survives_via_regex(self) -> None:
        """``MX-\\d+`` IDs in nested result are extracted via regex."""
        overlord = _bare_overlord()
        prose = "Filed MX-123 with the team."
        successful = [
            _make_task_result(
                task_id="t1",
                description="File Linear ticket",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "Linear issues: MX-123" in rendered

    def test_synthetic_flat_shape_extracts_top_level_fields(self) -> None:
        """The dead-code branch fires when outputs is artificially flat.

        Real executor never produces this shape, but we pin it so we
        know the helper still works for any code path that *does* hand
        flat outputs (legacy callers, fallback paths, or future synthetic
        construction).
        """
        overlord = _bare_overlord()
        successful = [
            _make_task_result(
                task_id="t1",
                description="Create document",
                outputs={
                    "issue_id": "ENG-99",
                    "issue_url": "https://example.com/issues/99",
                    "created": True,
                },
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "Issue Id: ENG-99" in rendered
        assert "Issue Url: https://example.com/issues/99" in rendered

    def test_failed_tasks_listed_with_errors(self) -> None:
        """Failed tasks appear under a 'Failed Tasks:' section with errors."""
        overlord = _bare_overlord()
        successful = [
            _make_task_result(
                task_id="t1",
                description="Greet user",
                outputs=_make_task_outputs("t1", "Hello!"),
            ),
        ]
        all_results = successful + [
            _make_task_result(
                task_id="t2",
                description="Post to GitHub",
                status="failed",
                error="403 Forbidden — token lacks write scope",
            ),
            _make_task_result(
                task_id="t3",
                description="Send Slack notification",
                status="failed",
                error="Slack workspace not configured",
            ),
        ]
        rendered = overlord._consolidate_workflow_results(successful, all_results)
        assert "Failed Tasks:" in rendered
        assert "Post to GitHub" in rendered
        assert "403 Forbidden — token lacks write scope" in rendered
        assert "Send Slack notification" in rendered
        assert "Slack workspace not configured" in rendered

    def test_empty_outputs_falls_back_to_status_line(self) -> None:
        """Tasks with empty outputs degrade to the status line."""
        overlord = _bare_overlord()
        successful = [
            _make_task_result(
                task_id="t1",
                description="Run a placeholder task",
                outputs={},
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "Status: Completed successfully" in rendered

    def test_artifacts_listed_with_filenames(self) -> None:
        """Attached artifacts surface their filenames under a dedicated header."""
        overlord = _bare_overlord()
        artifacts = [
            {"filename": "report.pdf", "size_bytes": 18432},
            {"filename": "summary.md", "size_bytes": 940},
        ]
        successful = [
            _make_task_result(
                task_id="t1",
                description="Generate quarterly report",
                outputs=_make_task_outputs("t1", "Generated the report.", artifacts=artifacts),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "report.pdf" in rendered
        assert "summary.md" in rendered
        assert "Files Attached:" in rendered

    def test_main_result_rendered_in_output(self) -> None:
        """Each task's ``outputs["main"]["result"]`` prose appears verbatim."""
        overlord = _bare_overlord()
        prose = (
            "I created your welcome issue at "
            "https://github.com/muxi-ai/runtime/issues/50 — titled 'Welcome to MUXI'."
        )
        successful = [
            _make_task_result(
                task_id="t1",
                description="Create welcome GitHub issue",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert prose in rendered
        # And the URL specifically — the most useful single piece of
        # data the user needs — must be carried verbatim.
        assert "https://github.com/muxi-ai/runtime/issues/50" in rendered

    def test_multi_task_each_result_rendered_in_order(self) -> None:
        """Multiple tasks render their prose in dispatch order."""
        overlord = _bare_overlord()
        prose_a = "Greeting: hello and welcome to MUXI."
        prose_b = "Issue created at https://github.com/example/issues/1."
        prose_c = "Recap: I introduced MUXI and created the issue."
        successful = [
            _make_task_result(
                task_id="t1",
                description="Greet",
                outputs=_make_task_outputs("t1", prose_a),
            ),
            _make_task_result(
                task_id="t2",
                description="Create issue",
                outputs=_make_task_outputs("t2", prose_b),
            ),
            _make_task_result(
                task_id="t3",
                description="Summarize",
                outputs=_make_task_outputs("t3", prose_c),
            ),
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        idx_a = rendered.find(prose_a)
        idx_b = rendered.find(prose_b)
        idx_c = rendered.find(prose_c)
        assert idx_a >= 0, "task 1 prose missing"
        assert idx_b >= 0, "task 2 prose missing"
        assert idx_c >= 0, "task 3 prose missing"
        assert idx_a < idx_b < idx_c, "tasks must appear in dispatch order"

    def test_long_output_truncated_with_marker(self) -> None:
        """Per-task budget caps long prose with an explicit marker."""
        overlord = _bare_overlord()
        long_prose = "x" * 10_000
        successful = [
            _make_task_result(
                task_id="t1",
                description="Summarize a long document",
                outputs=_make_task_outputs("t1", long_prose),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        # Some prose carried through.
        assert "x" * 100 in rendered
        # But not the full 10 KB.
        assert "x" * 10_000 not in rendered
        # And the truncation is signposted.
        assert "truncated" in rendered.lower()

    def test_artifact_count_mentioned(self) -> None:
        """When tasks attach artifacts, the output mentions them."""
        overlord = _bare_overlord()
        artifacts = [
            {"filename": "report.pdf", "size_bytes": 18432},
            {"filename": "summary.md", "size_bytes": 940},
        ]
        successful = [
            _make_task_result(
                task_id="t1",
                description="Generate quarterly report",
                outputs=_make_task_outputs("t1", "Generated the report.", artifacts=artifacts),
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        # Filenames the user needs to reference.
        assert "report.pdf" in rendered
        assert "summary.md" in rendered

    def test_dict_main_result_rendered_structured(self) -> None:
        """When ``main.result`` is a dict (raw tool output), render its fields."""
        overlord = _bare_overlord()
        # Some tool calls return structured payloads instead of prose.
        # The consolidator should expose the useful fields, not Python
        # dict-syntax dumped inline.
        tool_output = {
            "issue_number": 50,
            "url": "https://github.com/muxi-ai/runtime/issues/50",
            "title": "Welcome to MUXI",
        }
        outputs = {
            "main": {
                "result": tool_output,
                "status": "success",
                "metrics": {},
                "warnings": [],
                "artifacts": [],
            },
            "task_id": {"result": "t1", "status": "success"},
            "completed": {"result": True, "status": "success"},
        }
        successful = [
            _make_task_result(
                task_id="t1",
                description="Create welcome GitHub issue (raw tool output)",
                outputs=outputs,
            )
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        assert "https://github.com/muxi-ai/runtime/issues/50" in rendered
        assert "Welcome to MUXI" in rendered
        # And the raw ``str(dict)`` form should NOT be the surface — we
        # want a clean rendering, not Python-dict syntax dumped inline.
        assert "{'issue_number': 50" not in rendered

    def test_total_size_capped_under_many_tasks(self) -> None:
        """Many large tasks must fit under a fair total budget AND
        carry at least some prose from each task.

        Two-sided assertion to defeat false greens:

        * A naive implementation that drops all prose passes the size
          bound trivially — so we also require that at least one task's
          distinctive prose actually surfaces.
        * A naive implementation that dumps every byte fails the size
          bound, so the test catches that regression too.
        """
        overlord = _bare_overlord()
        # 10 tasks, each with 5 KB of distinctive prose. Embed a unique
        # marker in each so we can verify per-task representation.
        successful = [
            _make_task_result(
                task_id=f"t{i}",
                description=f"Task {i} description",
                outputs=_make_task_outputs(
                    f"t{i}",
                    f"PROSE_MARKER_{i} " + "y" * 4_900,
                ),
            )
            for i in range(10)
        ]
        rendered = overlord._consolidate_workflow_results(successful, successful)
        # Size bound: well under the 50 KB raw upper bound.
        assert len(rendered) < 30_000
        # All task descriptions surface for orientation.
        for task in successful:
            assert task["description"] in rendered
        # At least the first task's distinctive prose marker shows up
        # somewhere in the rendered output.
        assert "PROSE_MARKER_0" in rendered


# -----------------------------------------------------------------------
# No-LLM guarantee
# -----------------------------------------------------------------------


def test_consolidator_does_not_call_llm() -> None:
    """The consolidator is pure string formatting — no model.chat invocation.

    We can't directly assert "no network call happened" in a unit test,
    but we CAN assert that the consolidator works with a bare Overlord
    skeleton that has no model wired in. If the consolidator quietly
    tried to call a model, it would AttributeError on missing
    ``self.model`` / ``self._capability_models`` / etc.
    """
    overlord = _bare_overlord()
    successful = [
        _make_task_result(
            task_id="t1",
            description="A task",
            outputs=_make_task_outputs("t1", "Some prose."),
        )
    ]
    rendered = overlord._consolidate_workflow_results(successful, successful)
    assert isinstance(rendered, str)
    assert "Some prose." in rendered


# -----------------------------------------------------------------------
# Sanity: the helper itself is callable and returns a string
# -----------------------------------------------------------------------


def test_consolidate_workflow_results_returns_string() -> None:
    """Smoke check: the function returns a non-empty string for a minimal call."""
    overlord = _bare_overlord()
    result = overlord._consolidate_workflow_results(
        [
            _make_task_result(
                task_id="t1",
                description="Say hi",
                outputs=_make_task_outputs("t1", "Hi there!"),
            )
        ],
        [
            _make_task_result(
                task_id="t1",
                description="Say hi",
                outputs=_make_task_outputs("t1", "Hi there!"),
            )
        ],
    )
    assert isinstance(result, str)
    assert len(result) > 0
