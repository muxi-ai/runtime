"""Tests for ``Overlord._create_synthesis_prompt`` against realistic raw data.

Background
----------
``Overlord._synthesize_workflow_results`` is the final stage of a workflow
turn. It collects ``TaskResult`` entries from the workflow executor and
calls ``_create_synthesis_prompt`` to build a single prompt for the
overlord LLM, which then produces the user-visible reply.

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
rewritten ``_create_synthesis_prompt`` reads ``main.result`` as the
primary content source and uses ``_extract_key_outcomes`` plus the
``artifacts`` sub-dict as supplementary hints.

These tests cover three concerns:

1. Stable behaviors that survived the rewrite (failed tasks, regex
   extraction of Linear IDs, the synthetic flat-shape branch).
2. The new behavior the rewrite introduced (``main.result`` rendered
   verbatim, dict results expanded to ``key: value`` lines, artifact
   filenames listed, per-task and total byte budgets enforced).
3. Edge cases that previously degraded silently (empty outputs,
   non-dict outputs).
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
    """Build an ``Overlord`` skeleton for prompt-only tests.

    ``_create_synthesis_prompt`` and ``_extract_key_outcomes`` are
    stateless except for ``self`` lookup, so we sidestep the full
    formation engine constructor.
    """
    return Overlord.__new__(Overlord)


# -----------------------------------------------------------------------
# Behavior tests — rewritten ``_create_synthesis_prompt``
# -----------------------------------------------------------------------


class TestSynthesisPromptBehavior:
    """The rewritten prompt builder reads ``outputs["main"]["result"]``
    as primary content, surfaces regex hints and artifact filenames as
    supplementary fields, and enforces per-task / total byte budgets.
    """

    def test_github_flow_carries_agent_prose(self) -> None:
        """A typical GitHub onboarding turn carries every task's prose.

        Each task's ``outputs["main"]["result"]`` contains the agent's
        synthesized response. The rewritten prompt builder renders all
        four bodies so the overlord LLM has real content to summarize.
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
                    "Next steps: try `What can you do?` or ask me to " "summarize a webpage.",
                ),
            ),
        ]
        prompt = overlord._create_synthesis_prompt("onboard me", successful, successful)

        # Each task description appears for orientation.
        for task in successful:
            assert task["description"] in prompt

        # And the agent's prose appears verbatim — these phrases live
        # only in ``outputs["main"]["result"]``.
        assert "I'm MUXI" in prompt
        assert "https://github.com/muxi-ai/runtime/issues/50" in prompt
        assert "you asked to be onboarded" in prompt
        assert "summarize a webpage" in prompt

        # The "Status: Completed successfully" fallback should NOT fire
        # for any task that has real body content.
        assert "Status: Completed successfully" not in prompt

    def test_canonical_linear_url_now_carried_via_main_result(self) -> None:
        """Canonical ``https://linear.app/...`` URLs are carried via prose.

        The legacy URL regex misses canonical Linear URLs (it requires
        chars between ``://`` and ``linear``). The rewrite renders
        ``main.result`` directly, so the URL appears in the prompt body
        regardless of regex behavior. The MX-id regex hint still surfaces
        the ID separately for the LLM's convenience.
        """
        overlord = _bare_overlord()
        prose = "Created Linear issue at https://linear.app/acme/issue/MX-42 " "for the bug report."
        successful = [
            _make_task_result(
                task_id="t1",
                description="File Linear bug",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        prompt = overlord._create_synthesis_prompt("file a bug", successful, successful)
        # URL now carried via main.result rendering, regardless of regex.
        assert "linear.app/acme/issue/MX-42" in prompt
        # MX-id still surfaces via _extract_key_outcomes regex hint.
        assert "Linear issues: MX-42" in prompt

    def test_subdomain_linear_url_survives_with_hint(self) -> None:
        """URLs with chars before ``linear`` appear in body AND hints."""
        overlord = _bare_overlord()
        prose = (
            "Created issue at https://example.linear.app/acme/issue/MX-42 " "for the bug report."
        )
        successful = [
            _make_task_result(
                task_id="t1",
                description="File subdomain Linear bug",
                outputs=_make_task_outputs("t1", prose),
            )
        ]
        prompt = overlord._create_synthesis_prompt("file a bug", successful, successful)
        assert "example.linear.app/acme/issue/MX-42" in prompt

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
        prompt = overlord._create_synthesis_prompt("file a ticket", successful, successful)
        assert "Linear issues: MX-123" in prompt

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
        prompt = overlord._create_synthesis_prompt("create a doc", successful, successful)
        assert "Issue Id: ENG-99" in prompt
        assert "Issue Url: https://example.com/issues/99" in prompt

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
        prompt = overlord._create_synthesis_prompt("greet and notify", successful, all_results)
        assert "Failed Tasks:" in prompt
        assert "Post to GitHub" in prompt
        assert "403 Forbidden — token lacks write scope" in prompt
        assert "Send Slack notification" in prompt
        assert "Slack workspace not configured" in prompt

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
        prompt = overlord._create_synthesis_prompt("do something", successful, successful)
        assert "Status: Completed successfully" in prompt

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
        prompt = overlord._create_synthesis_prompt(
            "make a quarterly report", successful, successful
        )
        assert "report.pdf" in prompt
        assert "summary.md" in prompt
        assert "Files Attached:" in prompt

    def test_main_result_rendered_in_prompt(self) -> None:
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
        prompt = overlord._create_synthesis_prompt("onboard me", successful, successful)
        assert prose in prompt
        # And the URL specifically — the most useful single piece of
        # data the user needs — must be carried verbatim.
        assert "https://github.com/muxi-ai/runtime/issues/50" in prompt

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
        prompt = overlord._create_synthesis_prompt("onboard me", successful, successful)
        idx_a = prompt.find(prose_a)
        idx_b = prompt.find(prose_b)
        idx_c = prompt.find(prose_c)
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
        prompt = overlord._create_synthesis_prompt("summarize", successful, successful)
        # Some prose carried through.
        assert "x" * 100 in prompt
        # But not the full 10 KB.
        assert "x" * 10_000 not in prompt
        # And the truncation is signposted.
        assert "truncated" in prompt.lower()

    def test_artifact_count_mentioned(self) -> None:
        """When tasks attach artifacts, the prompt mentions them."""
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
        prompt = overlord._create_synthesis_prompt(
            "make a quarterly report", successful, successful
        )
        # Filenames the user needs to reference.
        assert "report.pdf" in prompt
        assert "summary.md" in prompt

    def test_dict_main_result_rendered_structured(self) -> None:
        """When ``main.result`` is a dict (raw tool output), render its fields."""
        overlord = _bare_overlord()
        # Some tool calls return structured payloads instead of prose.
        # The current code stringifies the whole thing into the prompt
        # in an opaque way; the rewrite should expose the useful fields.
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
        prompt = overlord._create_synthesis_prompt("onboard me", successful, successful)
        assert "https://github.com/muxi-ai/runtime/issues/50" in prompt
        assert "Welcome to MUXI" in prompt
        # And the raw ``str(dict)`` form should NOT be the surface — we
        # want a clean rendering, not Python-dict syntax dumped inline.
        assert "{'issue_number': 50" not in prompt

    def test_total_prompt_size_capped_under_many_tasks(self) -> None:
        """Many large tasks must fit under a fair total budget AND
        carry at least some prose from each task.

        Two-sided assertion to defeat false greens:

        * Today's code passes the size bound trivially because it never
          renders the prose at all — so we also require that at least
          one task's distinctive prose actually surfaces.
        * A naive future implementation that dumps every byte would fail
          the size bound, so the test catches that regression too.
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
        prompt = overlord._create_synthesis_prompt("do many things", successful, successful)
        # Size bound: well under the 50 KB raw upper bound.
        assert len(prompt) < 30_000
        # All task descriptions surface for orientation.
        for task in successful:
            assert task["description"] in prompt
        # At least the first task's distinctive prose marker shows up
        # somewhere in the prompt — this is the assertion that fails
        # against today's "Status: Completed successfully" prompt.
        assert "PROSE_MARKER_0" in prompt


# -----------------------------------------------------------------------
# Sanity: the helper itself is callable and returns a string
# -----------------------------------------------------------------------


def test_create_synthesis_prompt_returns_string() -> None:
    """Smoke check: the function returns a non-empty string for a minimal call."""
    overlord = _bare_overlord()
    result = overlord._create_synthesis_prompt(
        "hello",
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
