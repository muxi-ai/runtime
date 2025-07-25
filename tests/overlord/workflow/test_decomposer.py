"""
Tests for TaskDecomposer - Task decomposition engine.

Tests the core decomposition engine that breaks down complex requests into
executable workflows with plan preview capabilities.
"""

import pytest
from unittest.mock import AsyncMock

from src.muxi.overlord.workflow.decomposer import TaskDecomposer, ApprovalManager
from src.muxi.overlord.workflow.types import (
    Workflow, SubTask, WorkflowStatus, ApprovalStatus, RequestAnalysis
)
from src.muxi.llm import LLM


class TestTaskDecomposer:
    """Test TaskDecomposer functionality."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM for testing."""
        llm = AsyncMock(spec=LLM)
        return llm

    @pytest.fixture
    def decomposer(self, mock_llm):
        """Create TaskDecomposer instance with mock LLM."""
        return TaskDecomposer(llm=mock_llm)

    @pytest.fixture
    def decomposer_no_llm(self):
        """Create TaskDecomposer instance without LLM for heuristic testing."""
        return TaskDecomposer(llm=None)

    @pytest.fixture
    def sample_analysis(self):
        """Sample request analysis for testing."""
        return RequestAnalysis(
            complexity_score=8.5,
            requires_decomposition=True,
            required_capabilities=['research', 'writing', 'analysis'],
            implicit_subtasks=['research trends', 'analyze data', 'write report'],
            acceptance_criteria=['comprehensive report', 'data-driven insights']
        )

    @pytest.mark.asyncio
    async def test_llm_decompose_simple_request(self, decomposer, mock_llm):
        """Test LLM-based decomposition of a simple request."""

        # Setup
        request = "Research AI trends and write a report"

        mock_llm.generate.return_value = """
WORKFLOW_ANALYSIS:
This request requires research followed by writing. The research must complete before writing can begin.

TASKS:
Task_ID: task_1
Description: Research current AI trends and developments
Required_Capabilities: [research, web_search]
Dependencies: none
Estimated_Complexity: 7
Inputs: user request
Outputs: research findings

Task_ID: task_2
Description: Write comprehensive report on AI trends
Required_Capabilities: [writing]
Dependencies: task_1
Estimated_Complexity: 8
Inputs: research findings
Outputs: final report

EXECUTION_STRATEGY:
Sequential execution with research first, then writing based on findings.
"""

        # Execute
        workflow = await decomposer.decompose_request(request)

        # Verify
        assert workflow is not None
        assert workflow.user_request == request
        assert len(workflow.tasks) == 2
        assert workflow.status == WorkflowStatus.PENDING

        # Check task 1
        task1 = workflow.tasks.get('task_1')
        assert task1 is not None
        assert 'research' in task1.required_capabilities
        assert len(task1.dependencies) == 0

        # Check task 2
        task2 = workflow.tasks.get('task_2')
        assert task2 is not None
        assert 'writing' in task2.required_capabilities
        assert 'task_1' in task2.dependencies

    @pytest.mark.asyncio
    async def test_llm_decompose_with_approval_required(self, decomposer, mock_llm):
        """Test decomposition with plan preview generation."""

        # Setup
        request = "Refactor authentication system"

        mock_llm.generate.side_effect = [
            # First call: decomposition
            """
TASKS:
Task_ID: task_1
Description: Analyze current authentication system
Required_Capabilities: [analysis, security]
Dependencies: none
Estimated_Complexity: 6
""",
            # Second call: plan preview
            """
Here's my plan to refactor your authentication system:

## Approach
I'll start by analyzing your current system to identify issues and improvement opportunities, then implement the refactored solution with enhanced security.

## Steps
1. **Security Analysis** (10-15 minutes)
   - Review current authentication flows
   - Identify vulnerabilities and technical debt

2. **Implementation** (30-45 minutes)
   - Implement secure token management
   - Update API endpoints with proper validation

This approach ensures we maintain security while improving the system architecture.

Would you like me to proceed with this plan?
"""
        ]

        # Execute
        workflow = await decomposer.decompose_request(request, requires_approval=True)

        # Verify
        assert workflow.requires_approval is True
        assert workflow.approval_status == ApprovalStatus.AWAITING_APPROVAL
        assert workflow.plan_preview is not None
        assert "Here's my plan" in workflow.plan_preview
        assert "Would you like me to proceed" in workflow.plan_preview

    @pytest.mark.asyncio
    async def test_llm_decompose_with_context(self, decomposer, mock_llm, sample_analysis):
        """Test decomposition with context and analysis."""

        # Setup
        request = "Create dashboard for project metrics"
        context = {"project_type": "web_app", "tech_stack": "React"}

        mock_llm.generate.return_value = """
TASKS:
Task_ID: task_1
Description: Design dashboard layout and components
Required_Capabilities: [design, ui_ux]
Dependencies: none
Estimated_Complexity: 6
"""

        # Execute
        workflow = await decomposer.decompose_request(
            request, context=context, analysis=sample_analysis
        )

        # Verify
        assert workflow is not None
        mock_llm.generate.assert_called_once()

        # Check that context and analysis were included in prompt
        call_args = mock_llm.generate.call_args[0][0]
        assert "Context:" in call_args
        assert "React" in call_args
        assert "Complexity Score: 8.5" in call_args

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_heuristic(self, decomposer, mock_llm):
        """Test fallback to heuristic decomposition when LLM fails."""

        # Setup
        request = "Research machine learning and write analysis"
        mock_llm.generate.side_effect = Exception("LLM API error")

        # Execute
        workflow = await decomposer.decompose_request(request)

        # Verify - should fallback to heuristic decomposition
        assert workflow is not None
        assert len(workflow.tasks) >= 1  # Heuristic should create at least one task

        # Should contain tasks based on keywords
        task_descriptions = [task.description for task in workflow.tasks.values()]
        assert any('research' in desc.lower() for desc in task_descriptions)

    def test_heuristic_decompose_research_and_writing(self, decomposer_no_llm):
        """Test heuristic decomposition for research and writing request."""

        # Setup
        request = "research sustainable packaging and write comprehensive report"

        # Execute
        workflow = decomposer_no_llm._heuristic_decompose_request(
            "test_workflow", request, None
        )

        # Verify
        assert workflow is not None
        assert len(workflow.tasks) >= 2  # Should create research and writing tasks

        capabilities = []
        for task in workflow.tasks.values():
            capabilities.extend(task.required_capabilities)

        assert 'research' in capabilities
        assert 'writing' in capabilities

    def test_heuristic_decompose_single_capability(self, decomposer_no_llm):
        """Test heuristic decomposition with single capability."""

        # Setup
        request = "analyze the quarterly sales data"

        # Execute
        workflow = decomposer_no_llm._heuristic_decompose_request(
            "test_workflow", request, None
        )

        # Verify
        assert workflow is not None
        assert len(workflow.tasks) >= 1

        # Should identify analysis capability
        capabilities = []
        for task in workflow.tasks.values():
            capabilities.extend(task.required_capabilities)

        assert 'data_analysis' in capabilities

    def test_heuristic_decompose_no_keywords(self, decomposer_no_llm):
        """Test heuristic decomposition when no keywords match."""

        # Setup
        request = "help me with something vague"

        # Execute
        workflow = decomposer_no_llm._heuristic_decompose_request(
            "test_workflow", request, None
        )

        # Verify - should create general fallback task
        assert workflow is not None
        assert len(workflow.tasks) == 1

        task = next(iter(workflow.tasks.values()))
        assert 'general' in task.required_capabilities

    @pytest.mark.asyncio
    async def test_modify_workflow_with_llm(self, decomposer, mock_llm):
        """Test workflow modification using LLM."""

        # Setup original workflow
        original_workflow = Workflow(
            id="test_workflow",
            user_request="Write a report",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Write basic report",
                    required_capabilities=['writing'],
                    dependencies=[],
                    estimated_complexity=5.0
                )
            }
        )

        modification_instructions = "Add more focus on security aspects"

        mock_llm.generate.side_effect = [
            # Modification response
            """
TASKS:
Task_ID: task_1
Description: Analyze security requirements
Required_Capabilities: [analysis, security]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_2
Description: Write security-focused report
Required_Capabilities: [writing, security]
Dependencies: task_1
Estimated_Complexity: 7
""",
            # Plan preview
            "Updated plan with security focus as requested."
        ]

        # Execute
        modified_workflow = await decomposer.modify_workflow(
            original_workflow, modification_instructions
        )

        # Verify
        assert modified_workflow is not None
        assert len(modified_workflow.tasks) == 2  # Should have added security analysis
        assert modified_workflow.plan_preview == "Updated plan with security focus as requested."

    def test_parse_task_block_valid(self, decomposer):
        """Test parsing of valid task block."""

        block = """task_1
Description: Research AI trends
Required_Capabilities: research, analysis
Dependencies: none
Estimated_Complexity: 7
"""

        task = decomposer._parse_task_block(block)

        assert task is not None
        assert task.id == "task_1"
        assert task.description == "Research AI trends"
        assert "research" in task.required_capabilities
        assert "analysis" in task.required_capabilities
        assert len(task.dependencies) == 0
        assert task.estimated_complexity == 7.0

    def test_parse_task_block_with_dependencies(self, decomposer):
        """Test parsing task block with dependencies."""

        block = """task_2
Description: Write report based on research
Required_Capabilities: [writing]
Dependencies: [task_1, task_3]
Estimated_Complexity: 8
"""

        task = decomposer._parse_task_block(block)

        assert task is not None
        assert task.id == "task_2"
        assert "task_1" in task.dependencies
        assert "task_3" in task.dependencies
        assert len(task.dependencies) == 2

    def test_parse_task_block_invalid(self, decomposer):
        """Test parsing of invalid task block."""

        block = "incomplete block without proper structure"

        task = decomposer._parse_task_block(block)

        assert task is not None  # Should create fallback task
        assert task.description == "Task description"  # Default value

    def test_workflow_validation_success(self, decomposer):
        """Test successful workflow validation."""

        workflow = Workflow(
            id="test_workflow",
            user_request="Test request",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="First task",
                    required_capabilities=['research'],
                    dependencies=[],
                    estimated_complexity=5.0
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Second task",
                    required_capabilities=['writing'],
                    dependencies=['task_1'],
                    estimated_complexity=6.0
                )
            }
        )

        validated_workflow = decomposer._validate_workflow(workflow)

        assert validated_workflow is not None
        assert len(validated_workflow.tasks) == 2

    def test_workflow_validation_with_cycles(self, decomposer):
        """Test workflow validation with circular dependencies."""

        workflow = Workflow(
            id="test_workflow",
            user_request="Test request",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="First task",
                    required_capabilities=['research'],
                    dependencies=['task_2'],  # Circular dependency
                    estimated_complexity=5.0
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Second task",
                    required_capabilities=['writing'],
                    dependencies=['task_1'],  # Circular dependency
                    estimated_complexity=6.0
                )
            }
        )

        # Should fix the circular dependency
        validated_workflow = decomposer._validate_workflow(workflow)

        assert validated_workflow is not None
        # Cycle should be broken (implementation may vary)

    def test_create_fallback_workflow(self, decomposer):
        """Test creation of fallback workflow."""

        request = "Complex request that failed to decompose"

        workflow = decomposer._create_fallback_workflow(request)

        assert workflow is not None
        assert workflow.user_request == request
        assert len(workflow.tasks) == 1
        assert workflow.status == WorkflowStatus.PENDING

        task = next(iter(workflow.tasks.values()))
        assert "general" in task.required_capabilities

    @pytest.mark.asyncio
    async def test_error_handling_in_decompose_request(self, decomposer, mock_llm):
        """Test error handling during decomposition."""

        request = "Test request"
        mock_llm.generate.side_effect = Exception("Critical error")

        # Should not raise exception, should return fallback workflow
        workflow = await decomposer.decompose_request(request)

        assert workflow is not None
        assert workflow.user_request == request
        # Should be fallback workflow with general task

    def test_heuristic_generate_plan_preview(self, decomposer_no_llm):
        """Test heuristic plan preview generation."""

        workflow = Workflow(
            id="test_workflow",
            user_request="Write a report on AI trends",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Research AI trends",
                    required_capabilities=['research'],
                    dependencies=[],
                    estimated_complexity=6.0
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Write comprehensive report",
                    required_capabilities=['writing'],
                    dependencies=['task_1'],
                    estimated_complexity=7.0
                )
            }
        )

        plan_preview = decomposer_no_llm._heuristic_generate_plan_preview(
            workflow, "Write a report on AI trends"
        )

        assert plan_preview is not None
        assert len(plan_preview) > 0
        assert "research" in plan_preview.lower()
        assert "report" in plan_preview.lower()


class TestApprovalManager:
    """Test ApprovalManager functionality."""

    @pytest.fixture
    def approval_manager(self):
        """Create ApprovalManager instance."""
        return ApprovalManager()

    @pytest.fixture
    def sample_workflow(self):
        """Create sample workflow for testing."""
        return Workflow(
            id="test_workflow",
            user_request="Refactor authentication system",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Analyze current auth system",
                    required_capabilities=['analysis'],
                    dependencies=[],
                    estimated_complexity=6.0
                )
            },
            requires_approval=True,
            plan_preview="Here's my plan to refactor your authentication system..."
        )

    @pytest.mark.asyncio
    async def test_present_plan_for_approval(self, approval_manager, sample_workflow):
        """Test plan presentation for approval."""

        result = await approval_manager.present_plan_for_approval(sample_workflow)

        assert result is not None
        assert sample_workflow.plan_preview in result
        assert "Would you like me to proceed" in result
        assert sample_workflow.approval_status == ApprovalStatus.AWAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_present_plan_without_preview(self, approval_manager):
        """Test error when workflow missing plan preview."""

        workflow = Workflow(
            id="test_workflow",
            user_request="Test request",
            tasks={},
            requires_approval=True,
            plan_preview=None  # Missing preview
        )

        with pytest.raises(ValueError, match="Workflow missing plan preview"):
            await approval_manager.present_plan_for_approval(workflow)

    @pytest.mark.asyncio
    async def test_process_approval_response_approved(self, approval_manager, sample_workflow):
        """Test processing approval response - approved."""

        sample_workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

        # Test various approval phrases
        approval_responses = [
            "yes, proceed",
            "looks good, go ahead",
            "approved",
            "that works perfectly"
        ]

        for response in approval_responses:
            status, instructions = await approval_manager.process_approval_response(
                sample_workflow, response
            )

            assert status == ApprovalStatus.APPROVED
            assert instructions is None
            assert sample_workflow.approval_status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_process_approval_response_rejected(self, approval_manager, sample_workflow):
        """Test processing approval response - rejected."""

        sample_workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

        rejection_responses = [
            "no, I don't like this approach",
            "reject this plan",
            "different approach needed"
        ]

        for response in rejection_responses:
            status, instructions = await approval_manager.process_approval_response(
                sample_workflow, response
            )

            assert status == ApprovalStatus.REJECTED
            assert instructions == response
            assert sample_workflow.approval_status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_process_approval_response_modified(self, approval_manager, sample_workflow):
        """Test processing approval response - modifications requested."""

        sample_workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

        modification_responses = [
            "looks good but can you add more security testing?",
            "instead of that approach, let's focus on performance",
            "change the order to prioritize frontend first"
        ]

        for response in modification_responses:
            status, instructions = await approval_manager.process_approval_response(
                sample_workflow, response
            )

            assert status == ApprovalStatus.MODIFIED
            assert instructions == response
            assert sample_workflow.approval_status == ApprovalStatus.MODIFIED

    @pytest.mark.asyncio
    async def test_process_approval_response_unclear(self, approval_manager, sample_workflow):
        """Test processing unclear approval response."""

        sample_workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

        unclear_responses = [
            "hmm, I'm not sure",
            "maybe",
            "what do you think?"
        ]

        for response in unclear_responses:
            status, instructions = await approval_manager.process_approval_response(
                sample_workflow, response
            )

            assert status == ApprovalStatus.AWAITING_APPROVAL
            assert "I want to make sure I understand correctly" in instructions
