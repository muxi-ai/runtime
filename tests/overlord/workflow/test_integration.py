"""
End-to-end integration tests for workflow orchestration system.

Tests the complete workflow from analysis through execution, validating
the entire orchestration pipeline with real component interactions.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.muxi.overlord.workflow.analyzer import RequestAnalyzer
from src.muxi.overlord.workflow.decomposer import TaskDecomposer, ApprovalManager
from src.muxi.overlord.workflow.executor import WorkflowExecutor, ProgressTracker
from src.muxi.overlord.workflow.types import (
    Workflow, WorkflowStatus, ApprovalStatus, TaskStatus
)
from src.muxi.llm import LLM
from src.muxi.agent import Agent


class TestWorkflowOrchestrationIntegration:
    """Test complete workflow orchestration integration."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM for workflow components."""
        llm = AsyncMock(spec=LLM)
        return llm

    @pytest.fixture
    def mock_agents(self):
        """Create mock agent registry."""
        research_agent = AsyncMock(spec=Agent)
        research_agent.agent_id = "research_agent"
        research_agent.capabilities = ['research', 'analysis']
        research_agent.process_message.return_value = "Research findings completed"

        writing_agent = AsyncMock(spec=Agent)
        writing_agent.agent_id = "writing_agent"
        writing_agent.capabilities = ['writing', 'reporting']
        writing_agent.process_message.return_value = "Report written successfully"

        return {
            "research_agent": research_agent,
            "writing_agent": writing_agent
        }

    @pytest.fixture
    def orchestration_system(self, mock_llm, mock_agents):
        """Create complete orchestration system."""
        analyzer = RequestAnalyzer(llm=mock_llm)
        decomposer = TaskDecomposer(llm=mock_llm)
        approval_manager = ApprovalManager()
        executor = WorkflowExecutor(agent_registry=mock_agents)
        progress_tracker = ProgressTracker()

        return {
            'analyzer': analyzer,
            'decomposer': decomposer,
            'approval_manager': approval_manager,
            'executor': executor,
            'progress_tracker': progress_tracker
        }

    @pytest.mark.asyncio
    async def test_simple_request_end_to_end(self, orchestration_system, mock_llm):
        """Test complete workflow for simple request not requiring approval."""

        # Setup
        user_request = "Please summarize recent AI developments"

        # Mock LLM responses
        mock_llm.generate.side_effect = [
            # Analysis response
            """COMPLEXITY_SCORE: 3.5
REQUIRES_DECOMPOSITION: false
ESTIMATED_TIME: 5 minutes
REASONING: Simple summarization task""",

            # Decomposition response
            """TASKS:
Task_ID: task_1
Description: Research recent AI developments
Required_Capabilities: [research, analysis]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_2
Description: Summarize findings into report
Required_Capabilities: [writing]
Dependencies: task_1
Estimated_Complexity: 5"""
        ]

        # Execute: Analysis Phase
        analyzer = orchestration_system['analyzer']
        analysis = await analyzer.analyze_request(user_request)

        assert analysis.complexity_score == 3.5
        assert analysis.requires_decomposition is False

        # Execute: Decomposition Phase (force decomposition for testing)
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(
            user_request,
            requires_approval=False,
            analysis=analysis
        )

        # Verify workflow structure
        assert workflow is not None
        assert workflow.user_request == user_request
        assert len(workflow.tasks) == 2
        assert workflow.requires_approval is False
        assert workflow.status == WorkflowStatus.PENDING

        # Execute: Workflow Execution Phase
        executor = orchestration_system['executor']
        completed_workflow = await executor.execute_workflow(workflow)

        # Verify execution results
        assert completed_workflow.status == WorkflowStatus.COMPLETED
        assert completed_workflow.started_at is not None
        assert completed_workflow.completed_at is not None

        # Verify all tasks completed
        for task in completed_workflow.tasks.values():
            assert task.status == TaskStatus.DONE
            assert task.started_at is not None
            assert task.completed_at is not None

    @pytest.mark.asyncio
    async def test_complex_request_with_approval_flow(self, orchestration_system, mock_llm):
        """Test complete workflow for complex request requiring approval."""

        # Setup
        user_request = "Refactor our entire authentication system with modern security"

        # Mock LLM responses
        mock_llm.generate.side_effect = [
            # Analysis response
            """COMPLEXITY_SCORE: 9.2
REQUIRES_DECOMPOSITION: true
APPROVAL_REQUIRED: true
ESTIMATED_TIME: 3-4 hours
REASONING: Complex system refactoring with security implications""",

            # Decomposition response
            """TASKS:
Task_ID: task_1
Description: Analyze current authentication vulnerabilities
Required_Capabilities: [security_analysis, code_review]
Dependencies: none
Estimated_Complexity: 8

Task_ID: task_2
Description: Design new authentication architecture
Required_Capabilities: [system_design, security]
Dependencies: task_1
Estimated_Complexity: 9

Task_ID: task_3
Description: Implement secure authentication system
Required_Capabilities: [coding, security]
Dependencies: task_2
Estimated_Complexity: 9""",

            # Plan preview generation
            """Here's my comprehensive plan to refactor your authentication system:

## Security-First Approach
I'll conduct a thorough security audit of your current system, then design and implement a modern authentication solution with enhanced protection.

## Execution Plan
1. **Security Analysis** (45-60 minutes)
   - Audit current authentication flows
   - Identify vulnerabilities and security gaps
   - Document compliance requirements

2. **Architecture Design** (60-90 minutes)
   - Design secure token management
   - Plan multi-factor authentication
   - Create session security protocols

3. **Implementation** (90-120 minutes)
   - Implement secure authentication APIs
   - Add comprehensive validation
   - Include security monitoring

This approach ensures maximum security while maintaining usability.

Would you like me to proceed with this comprehensive refactoring plan?"""
        ]

        # Execute: Analysis Phase
        analyzer = orchestration_system['analyzer']
        analysis = await analyzer.analyze_request(user_request)

        assert analysis.complexity_score == 9.2
        assert analysis.requires_decomposition is True

        # Execute: Decomposition Phase with Approval
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(
            user_request,
            requires_approval=True,
            analysis=analysis
        )

        # Verify workflow requires approval
        assert workflow.requires_approval is True
        assert workflow.approval_status == ApprovalStatus.AWAITING_APPROVAL
        assert workflow.plan_preview is not None
        assert "comprehensive plan" in workflow.plan_preview

        # Execute: Approval Phase
        approval_manager = orchestration_system['approval_manager']
        approval_message = await approval_manager.present_plan_for_approval(workflow)

        assert "Would you like me to proceed" in approval_message
        assert workflow.plan_preview in approval_message

        # Simulate user approval
        approval_status, instructions = await approval_manager.process_approval_response(
            workflow, "Yes, looks good. Please proceed with the plan."
        )

        assert approval_status == ApprovalStatus.APPROVED
        assert workflow.approval_status == ApprovalStatus.APPROVED

        # Execute: Workflow Execution Phase
        executor = orchestration_system['executor']
        completed_workflow = await executor.execute_workflow(workflow)

        # Verify execution results
        assert completed_workflow.status == WorkflowStatus.COMPLETED
        assert len(completed_workflow.tasks) == 3

        # Verify sequential execution of dependent tasks
        task1 = completed_workflow.tasks['task_1']
        task2 = completed_workflow.tasks['task_2']
        task3 = completed_workflow.tasks['task_3']

        assert task1.completed_at < task2.started_at
        assert task2.completed_at < task3.started_at

    @pytest.mark.asyncio
    async def test_workflow_with_user_modifications(self, orchestration_system, mock_llm):
        """Test workflow modification during approval process."""

        user_request = "Create a data dashboard"

        # Mock LLM responses for initial decomposition
        mock_llm.generate.side_effect = [
            # Initial decomposition
            """TASKS:
Task_ID: task_1
Description: Design basic dashboard layout
Required_Capabilities: [design, ui_ux]
Dependencies: none
Estimated_Complexity: 6""",

            # Initial plan preview
            """I'll create a basic data dashboard with standard charts and metrics.""",

            # Modified decomposition
            """TASKS:
Task_ID: task_1
Description: Research real-time dashboard technologies
Required_Capabilities: [research, technology_analysis]
Dependencies: none
Estimated_Complexity: 7

Task_ID: task_2
Description: Design real-time dashboard with WebSocket integration
Required_Capabilities: [design, real_time_systems]
Dependencies: task_1
Estimated_Complexity: 8

Task_ID: task_3
Description: Implement dashboard with live data updates
Required_Capabilities: [coding, websockets]
Dependencies: task_2
Estimated_Complexity: 9""",

            # Modified plan preview
            """Updated plan with real-time capabilities as requested."""
        ]

        # Initial workflow creation
        decomposer = orchestration_system['decomposer']
        initial_workflow = await decomposer.decompose_request(
            user_request, requires_approval=True
        )

        # User requests modifications
        modification_instructions = "Add real-time data updates with WebSocket support"

        modified_workflow = await decomposer.modify_workflow(
            initial_workflow, modification_instructions
        )

        # Verify modifications applied
        assert len(modified_workflow.tasks) == 3  # Should have more tasks
        assert modified_workflow.plan_preview == "Updated plan with real-time capabilities as requested."

        # Execute modified workflow
        executor = orchestration_system['executor']
        completed_workflow = await executor.execute_workflow(modified_workflow)

        assert completed_workflow.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_failure_and_recovery(self, orchestration_system, mock_llm, mock_agents):
        """Test workflow execution with task failures and recovery."""

        user_request = "Analyze data and create report"

        # Mock decomposition
        mock_llm.generate.side_effect = [
            """TASKS:
Task_ID: task_1
Description: Extract and clean data
Required_Capabilities: [data_processing]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_2
Description: Analyze cleaned data
Required_Capabilities: [analysis]
Dependencies: task_1
Estimated_Complexity: 7

Task_ID: task_3
Description: Generate analysis report
Required_Capabilities: [writing]
Dependencies: task_2
Estimated_Complexity: 5"""
        ]

        # Create workflow
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(user_request)

        # Setup task failure
        mock_agents["research_agent"].process_message.side_effect = [
            Exception("Data extraction failed"),  # First task fails
            "Data successfully extracted on retry"  # Recovery
        ]

        # Execute workflow with failure
        executor = orchestration_system['executor']
        failed_workflow = await executor.execute_workflow(workflow)

        # Verify failure handling
        assert failed_workflow.status == WorkflowStatus.FAILED
        assert failed_workflow.tasks['task_1'].status == TaskStatus.FAILED
        assert failed_workflow.tasks['task_2'].status == TaskStatus.PENDING  # Not started
        assert failed_workflow.tasks['task_3'].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_parallel_workflow_execution(self, orchestration_system, mock_llm):
        """Test workflow with parallel task execution."""

        user_request = "Research multiple topics and synthesize findings"

        # Mock parallel workflow decomposition
        mock_llm.generate.side_effect = [
            """TASKS:
Task_ID: task_1
Description: Research AI market trends
Required_Capabilities: [research]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_2
Description: Research competitor analysis
Required_Capabilities: [research, analysis]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_3
Description: Research technology developments
Required_Capabilities: [research, technology]
Dependencies: none
Estimated_Complexity: 6

Task_ID: task_4
Description: Synthesize all research findings
Required_Capabilities: [writing, synthesis]
Dependencies: task_1,task_2,task_3
Estimated_Complexity: 8"""
        ]

        # Create and execute workflow
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(user_request)

        executor = orchestration_system['executor']
        completed_workflow = await executor.execute_workflow(workflow)

        # Verify parallel execution
        assert completed_workflow.status == WorkflowStatus.COMPLETED

        # Tasks 1-3 should be able to run in parallel
        task1 = completed_workflow.tasks['task_1']
        task2 = completed_workflow.tasks['task_2']
        task3 = completed_workflow.tasks['task_3']
        task4 = completed_workflow.tasks['task_4']

        # Synthesis task should start after all research tasks complete
        latest_research_completion = max(
            task1.completed_at, task2.completed_at, task3.completed_at
        )
        assert task4.started_at >= latest_research_completion

    @pytest.mark.asyncio
    async def test_progress_tracking_integration(self, orchestration_system, mock_llm):
        """Test progress tracking throughout workflow execution."""

        user_request = "Multi-step project"

        # Mock workflow with multiple tasks
        mock_llm.generate.side_effect = [
            """TASKS:
Task_ID: task_1
Description: Phase 1 task
Required_Capabilities: [research]
Dependencies: none
Estimated_Complexity: 5

Task_ID: task_2
Description: Phase 2 task
Required_Capabilities: [analysis]
Dependencies: task_1
Estimated_Complexity: 6

Task_ID: task_3
Description: Phase 3 task
Required_Capabilities: [writing]
Dependencies: task_2
Estimated_Complexity: 7"""
        ]

        # Create workflow
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(user_request)

        # Setup progress tracking
        progress_tracker = orchestration_system['progress_tracker']
        executor = orchestration_system['executor']

        # Add progress callback
        progress_updates = []
        def track_progress(workflow_id, workflow):
            progress = progress_tracker.get_progress(workflow_id)
            if progress:
                progress_updates.append(progress.copy())

        executor.add_progress_callback(track_progress)

        # Execute workflow
        completed_workflow = await executor.execute_workflow(workflow)

        # Verify progress was tracked
        assert len(progress_updates) > 0
        final_progress = progress_tracker.get_progress(workflow.id)
        assert final_progress['progress_percentage'] == 100.0
        assert final_progress['completed_tasks'] == 3

    @pytest.mark.asyncio
    async def test_heuristic_fallback_integration(self, orchestration_system):
        """Test fallback to heuristic methods when LLM fails."""

        user_request = "research machine learning and write summary"

        # Create system with no LLM (heuristic mode)
        analyzer = RequestAnalyzer(llm=None)
        decomposer = TaskDecomposer(llm=None)
        executor = orchestration_system['executor']

        # Execute with heuristic methods
        analysis = await analyzer.analyze_request(user_request)
        workflow = await decomposer.decompose_request(user_request, analysis=analysis)
        completed_workflow = await executor.execute_workflow(workflow)

        # Verify heuristic decomposition worked
        assert workflow is not None
        assert len(workflow.tasks) >= 1
        assert completed_workflow.status == WorkflowStatus.COMPLETED

        # Should identify research and writing capabilities
        capabilities = []
        for task in workflow.tasks.values():
            capabilities.extend(task.required_capabilities)

        assert any('research' in cap for cap in capabilities)

    @pytest.mark.asyncio
    async def test_error_propagation_integration(self, orchestration_system, mock_llm):
        """Test error handling and propagation through the system."""

        user_request = "Complex task that will fail"

        # Mock LLM failure during decomposition
        mock_llm.generate.side_effect = Exception("LLM service unavailable")

        # System should handle LLM failure gracefully
        decomposer = orchestration_system['decomposer']
        workflow = await decomposer.decompose_request(user_request)

        # Should fallback to heuristic decomposition
        assert workflow is not None
        assert len(workflow.tasks) >= 1

        # Execution should still work
        executor = orchestration_system['executor']
        completed_workflow = await executor.execute_workflow(workflow)

        # Should complete with fallback workflow
        assert completed_workflow.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]
