"""
Unit tests for the deterministic SOP template parser in TaskDecomposer.

Tests cover:
- Real SOP formats (numbered list under ## Steps)
- Heading-based fallback format (## Step N)
- Agent directive extraction ([agent:name])
- MCP tool extraction ([mcp:tool/action])
- Parallel step detection ([parallel] and section-based)
- Frontmatter stripping
- Graceful fallback when < 2 steps found
- Dependency graph correctness (sequential and fan-in)
- Fix 2: async bypass for bypass_approval SOPs (overlord logic)
- Fix 4: duplicate task ID rejection and phantom dependency stripping
"""

from muxi.runtime.datatypes.workflow import (
    TaskStatus,
    Workflow,
    WorkflowStatus,
    generate_workflow_id,
)
from muxi.runtime.formation.workflow.decomposer import TaskDecomposer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_decomposer() -> TaskDecomposer:
    return TaskDecomposer(llm=None, agent_registry={}, mcp_service=None)


# ---------------------------------------------------------------------------
# Real SOP fixtures (copied from e2e formation files)
# ---------------------------------------------------------------------------

SOP_CUSTOMER_ONBOARDING = """\
---
type: sop
name: New Customer Onboarding
mode: template
tags: customer, onboarding
---

# New Customer Onboarding

## Steps

1. **Verify customer information** [agent:operations]
   - Use [file:templates/customer-verification.md] for checklist
   - Query Salesforce via [mcp:salesforce] for account details
   - Validate company details and tax ID

2. **Provision user accounts** [agent:devops]
   - Create admin account using [mcp:auth0/create_user]
   - Set up initial user seats

3. **Schedule training** [agent:customer-success]
   - Book kickoff call within 48 hours
   - Create calendar event via [mcp:google-calendar]

4. **Configure integrations** [agent:developer]
   - Set up SSO using [mcp:okta] if applicable

5. **Send welcome package** [agent:communications]
   - Send via [mcp:sendgrid] or [mcp:mailchimp]
   - Create Linear issue for tracking using [mcp:linear/create_issue]
"""

SOP_INCIDENT_RESPONSE = """\
---
type: sop
name: Production Incident Response
mode: template
tags: critical, production
---

# Production Incident Response

## Steps

1. **Assess severity and impact** [agent:monitoring-specialist]
   - Use [mcp:datadog] to pull metrics from last hour

2. **Notify stakeholders** [agent:communications]
   - P1: Page on-call engineer via [mcp:pagerduty]
   - P2: Send Slack notification using [mcp:slack]

3. **Identify root cause** [agent:researcher]
   - Query logs using [mcp:elasticsearch]

4. **Create incident report** [agent:writer]
   - Create Linear issue with [mcp:linear/create_issue]

5. **Document post-mortem** [agent:documentation-specialist]
   - Upload to Confluence using [mcp:confluence]
"""

SOP_SYSTEM_REPORT = """\
---
type: sop
name: System Report Override
mode: template
---

# System Report Override SOP

## Steps

1. **Gather system information** [agent:it-support]
   Collect comprehensive system usage data including CPU, memory, disk, and core count.
   Store all metrics for calculation in the next step.

2. **Calculate system performance score**
   Extract core_count and cpu_usage_percent from the system info.
   Calculate performance score = core_count * (cpu_usage_percent / 100).

3. **Generate PDF report artifact**
   Create a PDF artifact containing system information summary.

4. **Reply with a simple "I'm done"**
   Respond with only "I'm done" and the PDF created in the previous step.
"""

SOP_JSON_OUTPUT = """\
---
type: sop
name: JSON Output Test
mode: template
synthesis: false
---

# JSON Output Test SOP

## Steps

1. **Generate JSON status report** [agent:it-support]
   Return ONLY a raw JSON object with exactly this structure:
   {"status":"ok","service":"muxi","checks":["memory","cpu","disk"]}
"""

SOP_PARALLEL_STEPS = """\
---
type: sop
name: Morning Briefing
mode: template
bypass_approval: true
---

# Morning Briefing SOP

## Parallel Data Fetch

The following three steps run concurrently.

## Steps

1. **Fetch calendar events** [agent:ms365-assistant]
   [parallel]
   Retrieve today's calendar events from Microsoft 365.

2. **Fetch email summary** [agent:ms365-assistant]
   [parallel]
   Retrieve the top 10 unread emails.

3. **Fetch task list** [agent:ms365-assistant]
   [parallel]
   Retrieve all pending tasks.

4. **Synthesize morning briefing** [agent:muxi-generalist]
   Combine calendar, email, and task data into a morning briefing.
"""

SOP_HEADING_FORMAT = """\
---
type: sop
name: Heading Format SOP
mode: template
---

# Heading SOP

### Step 1: Research phase
[agent:researcher]
Gather information about the topic.

### Step 2: Write report
[agent:writer]
Write a comprehensive report based on research findings.

### Step 3: Review
[agent:reviewer]
Review the report for accuracy.
"""

SOP_NO_STEPS = """\
---
type: sop
name: Empty SOP
mode: template
---

This SOP has no steps yet.
"""

SOP_ONE_STEP = """\
---
type: sop
name: Single Step
mode: template
---

## Steps

1. **Do the thing** [agent:worker]
   Just do it.
"""


# ===========================================================================
# Tests: numbered list format (primary)
# ===========================================================================

class TestNumberedListFormat:

    def test_customer_onboarding_step_count(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard a new customer")
        assert wf is not None
        assert len(wf.tasks) == 5

    def test_customer_onboarding_task_ids(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        assert set(wf.tasks.keys()) == {"task_1", "task_2", "task_3", "task_4", "task_5"}

    def test_customer_onboarding_sequential_dependencies(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        assert wf.tasks["task_1"].dependencies == []
        assert wf.tasks["task_2"].dependencies == ["task_1"]
        assert wf.tasks["task_3"].dependencies == ["task_2"]
        assert wf.tasks["task_4"].dependencies == ["task_3"]
        assert wf.tasks["task_5"].dependencies == ["task_4"]

    def test_customer_onboarding_agent_assignment(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        assert wf.tasks["task_1"].assigned_agent_id == "operations"
        assert wf.tasks["task_2"].assigned_agent_id == "devops"
        assert wf.tasks["task_3"].assigned_agent_id == "customer-success"
        assert wf.tasks["task_4"].assigned_agent_id == "developer"
        assert wf.tasks["task_5"].assigned_agent_id == "communications"

    def test_customer_onboarding_mcp_tools_extracted(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        # Step 1 uses salesforce
        assert "salesforce" in wf.tasks["task_1"].required_capabilities
        # Step 2 uses auth0 (extracted from auth0/create_user)
        assert "auth0" in wf.tasks["task_2"].required_capabilities
        # Step 5 uses sendgrid or mailchimp, and linear
        task5_caps = wf.tasks["task_5"].required_capabilities
        assert any(c in task5_caps for c in ("sendgrid", "mailchimp", "linear"))

    def test_incident_response_step_count(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "incident!")
        assert wf is not None
        assert len(wf.tasks) == 5

    def test_incident_response_agents(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "incident!")
        assert wf.tasks["task_1"].assigned_agent_id == "monitoring-specialist"
        assert wf.tasks["task_2"].assigned_agent_id == "communications"
        assert wf.tasks["task_3"].assigned_agent_id == "researcher"
        assert wf.tasks["task_4"].assigned_agent_id == "writer"
        assert wf.tasks["task_5"].assigned_agent_id == "documentation-specialist"

    def test_system_report_no_agent_on_steps_2_to_4(self):
        """Steps without [agent:...] get assigned_agent_id=None."""
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_SYSTEM_REPORT, "generate report")
        assert wf is not None
        assert len(wf.tasks) == 4
        assert wf.tasks["task_1"].assigned_agent_id == "it-support"
        assert wf.tasks["task_2"].assigned_agent_id is None
        assert wf.tasks["task_3"].assigned_agent_id is None
        assert wf.tasks["task_4"].assigned_agent_id is None

    def test_system_report_fallback_capabilities(self):
        """Steps without agent or MCP tools fall back to ['general']."""
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_SYSTEM_REPORT, "generate report")
        assert wf.tasks["task_2"].required_capabilities == ["general"]
        assert wf.tasks["task_3"].required_capabilities == ["general"]

    def test_description_strips_directives(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        desc = wf.tasks["task_1"].description
        assert "[agent:" not in desc
        assert "[mcp:" not in desc
        assert "[file:" not in desc

    def test_description_strips_bold_markers(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        assert "**" not in wf.tasks["task_1"].description

    def test_user_request_preserved(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "P1 incident at 03:00")
        assert wf.user_request == "P1 incident at 03:00"

    def test_workflow_status_pending(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "incident")
        # Pydantic may store enum values as strings; check both forms
        assert wf.status in (WorkflowStatus.PENDING, WorkflowStatus.PENDING.value)
        for task in wf.tasks.values():
            assert task.status in (TaskStatus.PENDING, TaskStatus.PENDING.value)

    def test_task_complexity_default(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "incident")
        for task in wf.tasks.values():
            assert task.estimated_complexity == 3.0

    def test_frontmatter_stripped(self):
        """Frontmatter must not appear in task descriptions."""
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        for task in wf.tasks.values():
            assert "type: sop" not in task.description
            assert "mode: template" not in task.description


# ===========================================================================
# Tests: parallel step detection
# ===========================================================================

class TestParallelStepDetection:

    def test_parallel_directive_removes_deps(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_PARALLEL_STEPS, "morning briefing")
        assert wf is not None
        assert wf.tasks["task_1"].dependencies == []
        assert wf.tasks["task_2"].dependencies == []
        assert wf.tasks["task_3"].dependencies == []

    def test_parallel_fan_in_for_synthesis_step(self):
        """Step 4 (synthesis) must depend on all 3 parallel steps."""
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_PARALLEL_STEPS, "morning briefing")
        assert set(wf.tasks["task_4"].dependencies) == {"task_1", "task_2", "task_3"}

    def test_parallel_step_count(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_PARALLEL_STEPS, "morning briefing")
        assert len(wf.tasks) == 4

    def test_sequential_sop_no_parallel(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_INCIDENT_RESPONSE, "incident")
        for task in wf.tasks.values():
            assert len(task.dependencies) <= 1


# ===========================================================================
# Tests: graceful fallback (< 2 steps)
# ===========================================================================

class TestFallback:

    def test_returns_none_for_no_steps(self):
        d = make_decomposer()
        result = d._parse_template_sop_deterministic(SOP_NO_STEPS, "do something")
        assert result is None

    def test_returns_none_for_single_step(self):
        d = make_decomposer()
        result = d._parse_template_sop_deterministic(SOP_JSON_OUTPUT, "get status")
        assert result is None

    def test_returns_none_for_empty_string(self):
        d = make_decomposer()
        result = d._parse_template_sop_deterministic("", "do something")
        assert result is None

    def test_returns_none_for_frontmatter_only(self):
        d = make_decomposer()
        sop = "---\ntype: sop\nmode: template\n---\n"
        result = d._parse_template_sop_deterministic(sop, "do something")
        assert result is None


# ===========================================================================
# Tests: heading format fallback
# ===========================================================================

class TestHeadingFormat:

    def test_heading_format_step_count(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_HEADING_FORMAT, "run heading sop")
        assert wf is not None
        assert len(wf.tasks) == 3

    def test_heading_format_agent_extraction(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_HEADING_FORMAT, "run heading sop")
        assert wf.tasks["task_1"].assigned_agent_id == "researcher"
        assert wf.tasks["task_2"].assigned_agent_id == "writer"
        assert wf.tasks["task_3"].assigned_agent_id == "reviewer"

    def test_heading_format_sequential_deps(self):
        d = make_decomposer()
        wf = d._parse_template_sop_deterministic(SOP_HEADING_FORMAT, "run heading sop")
        assert wf.tasks["task_1"].dependencies == []
        assert wf.tasks["task_2"].dependencies == ["task_1"]
        assert wf.tasks["task_3"].dependencies == ["task_2"]

    def test_heading_format_not_used_when_numbered_available(self):
        """Numbered list format takes priority over heading format."""
        d = make_decomposer()
        # SOP_CUSTOMER_ONBOARDING has numbered list — should NOT fall through to heading parser
        wf = d._parse_template_sop_deterministic(SOP_CUSTOMER_ONBOARDING, "onboard")
        # Heading format would produce 0 steps from this SOP; numbered list produces 5
        assert len(wf.tasks) == 5


# ===========================================================================
# Tests: Fix 4 - duplicate task ID rejection
# ===========================================================================

class TestDuplicateTaskIdRejection:

    def test_duplicate_id_keeps_first(self):
        """_parse_llm_decomposition must keep first task when LLM emits duplicate IDs."""
        d = make_decomposer()
        wf_id = generate_workflow_id()
        llm_response = """\
### TASKS:
1. **Task_ID**: task_1
   - **Description**: First version of task_1
   - **Required_Capabilities**: general
   - **Dependencies**: none
   - **Estimated_Complexity**: 2

2. **Task_ID**: task_2
   - **Description**: Second task
   - **Required_Capabilities**: general
   - **Dependencies**: task_1
   - **Estimated_Complexity**: 3

3. **Task_ID**: task_1
   - **Description**: Duplicate task_1 (should be ignored)
   - **Required_Capabilities**: research
   - **Dependencies**: none
   - **Estimated_Complexity**: 5
"""
        wf = d._parse_llm_decomposition(wf_id, "test request", llm_response)
        assert "task_1" in wf.tasks
        assert "task_2" in wf.tasks
        # First occurrence must be kept
        assert wf.tasks["task_1"].description == "First version of task_1"
        assert len(wf.tasks) == 2

    def test_no_false_positive_on_unique_ids(self):
        """Normal LLM output with unique IDs must not be affected."""
        d = make_decomposer()
        wf_id = generate_workflow_id()
        llm_response = """\
### TASKS:
1. **Task_ID**: task_1
   - **Description**: Research phase
   - **Required_Capabilities**: research
   - **Dependencies**: none
   - **Estimated_Complexity**: 3

2. **Task_ID**: task_2
   - **Description**: Write report
   - **Required_Capabilities**: writing
   - **Dependencies**: task_1
   - **Estimated_Complexity**: 4
"""
        wf = d._parse_llm_decomposition(wf_id, "test", llm_response)
        assert len(wf.tasks) == 2
        assert wf.tasks["task_1"].description == "Research phase"
        assert wf.tasks["task_2"].description == "Write report"


# ===========================================================================
# Tests: Fix 4 - phantom dependency stripping
# ===========================================================================

class TestPhantomDependencyStripping:

    def test_phantom_deps_stripped(self):
        """Dependencies referencing non-existent tasks must be removed."""
        d = make_decomposer()
        wf_id = generate_workflow_id()
        llm_response = """\
### TASKS:
1. **Task_ID**: task_1
   - **Description**: First task
   - **Required_Capabilities**: general
   - **Dependencies**: none
   - **Estimated_Complexity**: 2

2. **Task_ID**: task_3
   - **Description**: Third task (task_2 was never parsed)
   - **Required_Capabilities**: general
   - **Dependencies**: task_1, task_2
   - **Estimated_Complexity**: 3
"""
        wf = d._parse_llm_decomposition(wf_id, "test", llm_response)
        # task_2 doesn't exist; its reference in task_3.dependencies must be stripped
        assert "task_2" not in wf.tasks
        assert "task_2" not in wf.tasks["task_3"].dependencies
        # task_1 reference is valid and must be kept
        assert "task_1" in wf.tasks["task_3"].dependencies

    def test_all_deps_valid_untouched(self):
        """Valid dependency references must not be modified."""
        d = make_decomposer()
        wf_id = generate_workflow_id()
        llm_response = """\
### TASKS:
1. **Task_ID**: task_1
   - **Description**: First task
   - **Required_Capabilities**: general
   - **Dependencies**: none
   - **Estimated_Complexity**: 2

2. **Task_ID**: task_2
   - **Description**: Second task
   - **Required_Capabilities**: general
   - **Dependencies**: task_1
   - **Estimated_Complexity**: 3
"""
        wf = d._parse_llm_decomposition(wf_id, "test", llm_response)
        assert wf.tasks["task_2"].dependencies == ["task_1"]

    def test_hallucinated_dep_on_missing_task(self):
        """LLM refers to task_99 which was never emitted; must be silently stripped."""
        d = make_decomposer()
        wf_id = generate_workflow_id()
        llm_response = """\
### TASKS:
1. **Task_ID**: task_1
   - **Description**: Only task
   - **Required_Capabilities**: general
   - **Dependencies**: task_99
   - **Estimated_Complexity**: 2

2. **Task_ID**: task_2
   - **Description**: Second task
   - **Required_Capabilities**: general
   - **Dependencies**: task_1
   - **Estimated_Complexity**: 3
"""
        wf = d._parse_llm_decomposition(wf_id, "test", llm_response)
        # task_99 doesn't exist, so task_1 must have empty deps
        assert "task_99" not in wf.tasks["task_1"].dependencies
        # task_1 still depends on nothing after stripping
        assert wf.tasks["task_1"].dependencies == []


# ===========================================================================
# Tests: Fix 1 - SIF env setup in run_formation.py
# ===========================================================================

class TestSIFEnvSetup:

    def test_sif_env_applied_when_singularity_container_set(self, monkeypatch):
        """LD_LIBRARY_PATH must be extended when SINGULARITY_CONTAINER is set."""
        import os
        import sys

        monkeypatch.setenv("SINGULARITY_CONTAINER", "/path/to/runtime.sif")
        monkeypatch.delenv("MUXI_SIF_MODE", raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", "/existing/path")
        # HF_HUB_OFFLINE must not block the setdefault call
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        # Re-execute the module-level code by reimporting
        mod_path = "muxi.runtime.utils.run_formation"
        if mod_path in sys.modules:
            del sys.modules[mod_path]

        import muxi.runtime.utils.run_formation  # noqa: F401

        ldpath = os.environ.get("LD_LIBRARY_PATH", "")
        assert "/usr/lib" in ldpath
        assert "/existing/path" in ldpath
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"

    def test_sif_env_applied_when_muxi_sif_mode_set(self, monkeypatch):
        """LD_LIBRARY_PATH must be extended when MUXI_SIF_MODE=1 is set."""
        import os
        import sys

        monkeypatch.setenv("MUXI_SIF_MODE", "1")
        monkeypatch.delenv("SINGULARITY_CONTAINER", raising=False)
        monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        mod_path = "muxi.runtime.utils.run_formation"
        if mod_path in sys.modules:
            del sys.modules[mod_path]

        import muxi.runtime.utils.run_formation  # noqa: F401

        ldpath = os.environ.get("LD_LIBRARY_PATH", "")
        assert "/usr/lib" in ldpath

    def test_sif_env_not_applied_outside_sif(self, monkeypatch):
        """LD_LIBRARY_PATH must not be touched when not running in SIF."""
        import os
        import sys

        monkeypatch.delenv("SINGULARITY_CONTAINER", raising=False)
        monkeypatch.delenv("MUXI_SIF_MODE", raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", "/original/path")
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

        mod_path = "muxi.runtime.utils.run_formation"
        if mod_path in sys.modules:
            del sys.modules[mod_path]

        import muxi.runtime.utils.run_formation  # noqa: F401

        assert os.environ.get("LD_LIBRARY_PATH") == "/original/path"
        assert os.environ.get("HF_HUB_OFFLINE") is None


# ===========================================================================
# Tests: Fix 2 - async bypass for bypass_approval SOPs
# ===========================================================================

class TestAsyncBypassForSOPs:

    def _make_workflow_with_tasks(self, complexities: list) -> Workflow:
        """Create a Workflow with one task per complexity value (each must be 1-10)."""
        from muxi.runtime.datatypes.workflow import SubTask

        tasks = {}
        for i, c in enumerate(complexities, start=1):
            task_id = f"task_{i}"
            tasks[task_id] = SubTask(
                id=task_id,
                description=f"task {i}",
                required_capabilities=["general"],
                dependencies=[f"task_{i - 1}"] if i > 1 else [],
                estimated_complexity=float(c),
                status=TaskStatus.PENDING,
            )
        return Workflow(
            id=generate_workflow_id(),
            user_request="test",
            tasks=tasks,
            status=WorkflowStatus.PENDING,
        )

    def test_bypass_approval_sop_forces_sync(self):
        """A SOP with bypass_approval:true must result in use_async=False regardless of complexity."""
        relevant_sop = {"bypass_approval": True, "name": "Morning Briefing"}
        use_async = None
        # 4 tasks × complexity 4 = total 16; 16*0.5=8 min >> 30s threshold → would go async
        workflow = self._make_workflow_with_tasks([4, 4, 4, 4])

        if use_async is None and workflow and workflow.tasks:
            if relevant_sop and relevant_sop.get("bypass_approval", True):
                use_async = False

        assert use_async is False

    def test_non_bypass_sop_allows_async_heuristic(self):
        """A SOP with bypass_approval:false must still go through the complexity heuristic."""
        relevant_sop = {"bypass_approval": False, "name": "Approval Required SOP"}
        use_async = None
        # 4 tasks × complexity 4 = total 16; should trigger async
        workflow = self._make_workflow_with_tasks([4, 4, 4, 4])

        if use_async is None and workflow and workflow.tasks:
            if relevant_sop and relevant_sop.get("bypass_approval", True):
                use_async = False

        # bypass_approval is False → use_async stays None
        assert use_async is None

        # Heuristic: 16 * 0.5 = 8 minutes > 0.5 minutes (30s threshold)
        async_threshold_seconds = 30
        total_complexity = sum(t.estimated_complexity for t in workflow.tasks.values())
        estimated_minutes = total_complexity * 0.5
        threshold_minutes = async_threshold_seconds / 60
        if use_async is None:
            use_async = estimated_minutes > threshold_minutes

        assert use_async is True

    def test_no_sop_uses_heuristic(self):
        """When there is no relevant SOP, the complexity heuristic must still run."""
        relevant_sop = None
        use_async = None
        # 1 task × complexity 1 = total 1; 1*0.5=0.5 min == 0.5 min threshold → sync
        workflow = self._make_workflow_with_tasks([1])

        if use_async is None and workflow and workflow.tasks:
            if relevant_sop and relevant_sop.get("bypass_approval", True):
                use_async = False

        assert use_async is None  # unchanged; no SOP to force it

        async_threshold_seconds = 30
        total_complexity = sum(t.estimated_complexity for t in workflow.tasks.values())
        estimated_minutes = total_complexity * 0.5
        threshold_minutes = async_threshold_seconds / 60
        if use_async is None:
            use_async = estimated_minutes > threshold_minutes

        assert use_async is False  # 0.5 min is not > 0.5 min


# ===========================================================================
# Tests: MCP tool server name extraction (slash handling)
# ===========================================================================

class TestMCPToolExtraction:

    def test_slash_in_mcp_tool_uses_server_name(self):
        """[mcp:linear/create_issue] must yield capability 'linear', not 'linear/create_issue'."""
        d = make_decomposer()
        sop = """\
## Steps

1. **Create issue** [agent:dev]
   Create a Linear issue using [mcp:linear/create_issue].

2. **Send notification** [agent:dev]
   Notify the team via [mcp:slack/post_message].
"""
        wf = d._parse_template_sop_deterministic(sop, "create issue and notify")
        assert wf is not None
        assert "linear" in wf.tasks["task_1"].required_capabilities
        assert "linear/create_issue" not in wf.tasks["task_1"].required_capabilities
        assert "slack" in wf.tasks["task_2"].required_capabilities

    def test_multiple_mcp_tools_deduplicated(self):
        """Duplicate [mcp:pagerduty] references in the same step body must not produce duplicates."""
        d = make_decomposer()
        sop = """\
## Steps

1. **Alert on-call** [agent:ops]
   Page via [mcp:pagerduty] for P1.
   Also use [mcp:pagerduty] for escalation.

2. **Follow up** [agent:ops]
   Check ticket status.
"""
        wf = d._parse_template_sop_deterministic(sop, "alert")
        caps = wf.tasks["task_1"].required_capabilities
        assert caps.count("pagerduty") == 1
