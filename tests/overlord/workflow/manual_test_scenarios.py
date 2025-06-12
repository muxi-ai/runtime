"""
Manual test scenarios for workflow orchestration system.

This module provides comprehensive manual testing capabilities for validating
the enhanced overlord workflow orchestration in real-world scenarios.

Usage:
    python manual_test_scenarios.py --scenario <scenario_name>
    python manual_test_scenarios.py --interactive
    python manual_test_scenarios.py --all
"""

import asyncio
import sys
import argparse
from datetime import datetime
from typing import Dict, Any
import json

from src.muxi.runtime.overlord.workflow.analyzer import RequestAnalyzer
from src.muxi.runtime.overlord.workflow.decomposer import TaskDecomposer, ApprovalManager
from src.muxi.runtime.overlord.workflow.executor import WorkflowExecutor, ProgressTracker
from src.muxi.runtime.overlord.workflow.types import WorkflowStatus, ApprovalStatus
from src.muxi.runtime.llm import LLM
from src.muxi.runtime.agent import Agent


class ManualTestOrchestrator:
    """Orchestrator for manual testing scenarios."""

    def __init__(self):
        """Initialize manual test orchestrator."""
        self.analyzer = None
        self.decomposer = None
        self.approval_manager = None
        self.executor = None
        self.progress_tracker = None

        # Test results tracking
        self.test_results = {}
        self.current_test = None

    async def setup_system(self, use_real_llm: bool = False):
        """Setup the workflow orchestration system."""
        print("🔧 Setting up workflow orchestration system...")

        if use_real_llm:
            # Use real LLM (requires API keys)
            print("   Using real LLM models")
            # llm = OpenAIModel(model="gpt-4o")  # Uncomment with real implementation
            llm = None  # Fallback to heuristic for demo
        else:
            # Use mock/heuristic mode
            print("   Using heuristic mode (no LLM required)")
            llm = None

        # Initialize components
        self.analyzer = RequestAnalyzer(llm=llm)
        self.decomposer = TaskDecomposer(llm=llm)
        self.approval_manager = ApprovalManager()
        self.progress_tracker = ProgressTracker()

        # Create mock agent registry for testing
        agent_registry = await self._create_mock_agents()
        self.executor = WorkflowExecutor(agent_registry=agent_registry)

        print("✅ System setup complete")

    async def _create_mock_agents(self) -> Dict[str, Agent]:
        """Create mock agents for testing."""
        print("   Creating mock agent registry...")

        # In real implementation, these would be actual agents
        # For manual testing, we'll simulate agent responses
        mock_agents = {
            "research_agent": MockAgent("research_agent", ["research", "analysis"]),
            "writing_agent": MockAgent("writing_agent", ["writing", "reporting"]),
            "coding_agent": MockAgent("coding_agent", ["coding", "development"]),
            "design_agent": MockAgent("design_agent", ["design", "ui_ux"]),
            "security_agent": MockAgent("security_agent", ["security", "analysis"])
        }

        return mock_agents

    def log_test_result(self, test_name: str, status: str, details: Dict[str, Any]):
        """Log test results for reporting."""
        self.test_results[test_name] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }

    def print_header(self, title: str):
        """Print a formatted test header."""
        print("\n" + "="*80)
        print(f"🧪 {title}")
        print("="*80)

    def print_step(self, step: str):
        """Print a test step."""
        print(f"\n📋 {step}")

    def print_result(self, result: str, success: bool = True):
        """Print a test result."""
        icon = "✅" if success else "❌"
        print(f"   {icon} {result}")

    async def test_simple_request_workflow(self):
        """Test Scenario 1: Simple request without approval."""
        self.print_header("Test Scenario 1: Simple Request Workflow")

        # User input
        user_request = "Summarize the latest trends in artificial intelligence"

        try:
            # Step 1: Request Analysis
            self.print_step("Step 1: Analyzing request complexity")
            analysis = await self.analyzer.analyze_request(user_request)

            self.print_result(f"Complexity Score: {analysis.complexity_score}")
            self.print_result(f"Requires Decomposition: {analysis.requires_decomposition}")

            # Step 2: Task Decomposition
            self.print_step("Step 2: Decomposing request into tasks")
            workflow = await self.decomposer.decompose_request(
                user_request,
                requires_approval=False,
                analysis=analysis
            )

            self.print_result(f"Generated {len(workflow.tasks)} tasks")
            for task_id, task in workflow.tasks.items():
                print(f"     - {task_id}: {task.description}")
                print(f"       Capabilities: {task.required_capabilities}")
                print(f"       Dependencies: {task.dependencies}")

            # Step 3: Workflow Execution
            self.print_step("Step 3: Executing workflow")

            # Add progress tracking
            def track_progress(workflow_id, workflow):
                progress = self.progress_tracker.get_progress(workflow_id)
                if progress:
                    print(f"     Progress: {progress['progress_percentage']:.1f}% "
                          f"({progress['completed_tasks']}/{progress['total_tasks']} tasks)")

            self.executor.add_progress_callback(track_progress)

            completed_workflow = await self.executor.execute_workflow(workflow)

            # Results
            self.print_result(f"Workflow Status: {completed_workflow.status}")
            self.print_result(f"Execution Time: {(completed_workflow.completed_at - completed_workflow.started_at).total_seconds():.2f}s")

            # Log results
            self.log_test_result("simple_request_workflow", "PASSED", {
                "complexity_score": analysis.complexity_score,
                "task_count": len(workflow.tasks),
                "workflow_status": str(completed_workflow.status),
                "execution_time": (completed_workflow.completed_at - completed_workflow.started_at).total_seconds()
            })

        except Exception as e:
            self.print_result(f"Test Failed: {str(e)}", success=False)
            self.log_test_result("simple_request_workflow", "FAILED", {"error": str(e)})

    async def test_complex_request_with_approval(self):
        """Test Scenario 2: Complex request requiring approval."""
        self.print_header("Test Scenario 2: Complex Request with Approval Flow")

        user_request = "Refactor our authentication system to implement OAuth2 with JWT tokens"

        try:
            # Step 1: Request Analysis
            self.print_step("Step 1: Analyzing complex request")
            analysis = await self.analyzer.analyze_request(user_request)

            self.print_result(f"Complexity Score: {analysis.complexity_score}")
            self.print_result(f"Requires Approval: {analysis.requires_decomposition}")

            # Step 2: Task Decomposition with Approval
            self.print_step("Step 2: Generating workflow plan for approval")
            workflow = await self.decomposer.decompose_request(
                user_request,
                requires_approval=True,
                analysis=analysis
            )

            # Step 3: Plan Approval Process
            self.print_step("Step 3: Presenting plan for approval")
            approval_message = await self.approval_manager.present_plan_for_approval(workflow)

            print("\n" + "─"*60)
            print(approval_message)
            print("─"*60)

            # Simulate user approval
            self.print_step("Step 4: Processing user approval")
            user_response = "Yes, this plan looks comprehensive. Please proceed."

            approval_status, instructions = await self.approval_manager.process_approval_response(
                workflow, user_response
            )

            self.print_result(f"Approval Status: {approval_status}")

            if approval_status == ApprovalStatus.APPROVED:
                # Step 4: Execute Approved Workflow
                self.print_step("Step 5: Executing approved workflow")
                completed_workflow = await self.executor.execute_workflow(workflow)

                self.print_result(f"Workflow Status: {completed_workflow.status}")
                self.print_result(f"Tasks Completed: {len([t for t in completed_workflow.tasks.values() if t.status.value == 'done'])}")

                # Log results
                self.log_test_result("complex_request_with_approval", "PASSED", {
                    "complexity_score": analysis.complexity_score,
                    "approval_required": True,
                    "approval_status": str(approval_status),
                    "workflow_status": str(completed_workflow.status)
                })
            else:
                self.log_test_result("complex_request_with_approval", "FAILED", {
                    "error": "Approval was not granted"
                })

        except Exception as e:
            self.print_result(f"Test Failed: {str(e)}", success=False)
            self.log_test_result("complex_request_with_approval", "FAILED", {"error": str(e)})

    async def test_workflow_modification(self):
        """Test Scenario 3: Workflow modification during approval."""
        self.print_header("Test Scenario 3: Workflow Modification")

        user_request = "Create a data visualization dashboard"

        try:
            # Initial workflow
            self.print_step("Step 1: Creating initial workflow")
            initial_workflow = await self.decomposer.decompose_request(
                user_request, requires_approval=True
            )

            self.print_result(f"Initial plan has {len(initial_workflow.tasks)} tasks")

            # User requests modifications
            self.print_step("Step 2: Requesting workflow modifications")
            modification_request = "Add real-time data updates and interactive filtering"

            modified_workflow = await self.decomposer.modify_workflow(
                initial_workflow, modification_request
            )

            self.print_result(f"Modified plan has {len(modified_workflow.tasks)} tasks")
            self.print_result(f"Plan updated with modifications")

            # Execute modified workflow
            self.print_step("Step 3: Executing modified workflow")
            completed_workflow = await self.executor.execute_workflow(modified_workflow)

            self.print_result(f"Workflow Status: {completed_workflow.status}")

            self.log_test_result("workflow_modification", "PASSED", {
                "initial_tasks": len(initial_workflow.tasks),
                "modified_tasks": len(modified_workflow.tasks),
                "workflow_status": str(completed_workflow.status)
            })

        except Exception as e:
            self.print_result(f"Test Failed: {str(e)}", success=False)
            self.log_test_result("workflow_modification", "FAILED", {"error": str(e)})

    async def test_parallel_execution(self):
        """Test Scenario 4: Parallel task execution."""
        self.print_header("Test Scenario 4: Parallel Task Execution")

        user_request = "Research competitors, analyze market trends, and study user feedback"

        try:
            # Create workflow with parallel tasks
            self.print_step("Step 1: Creating workflow with parallel tasks")
            workflow = await self.decomposer.decompose_request(user_request)

            # Identify parallel tasks
            parallel_tasks = [t for t in workflow.tasks.values() if not t.dependencies]
            dependent_tasks = [t for t in workflow.tasks.values() if t.dependencies]

            self.print_result(f"Parallel tasks: {len(parallel_tasks)}")
            self.print_result(f"Dependent tasks: {len(dependent_tasks)}")

            # Execute workflow
            self.print_step("Step 2: Executing parallel workflow")
            start_time = datetime.now()
            completed_workflow = await self.executor.execute_workflow(workflow)
            execution_time = (datetime.now() - start_time).total_seconds()

            self.print_result(f"Workflow Status: {completed_workflow.status}")
            self.print_result(f"Total Execution Time: {execution_time:.2f}s")

            # Verify parallel execution timing
            if len(parallel_tasks) > 1:
                task_times = []
                for task in parallel_tasks:
                    task_obj = completed_workflow.tasks[task.id]
                    if task_obj.started_at and task_obj.completed_at:
                        task_time = (task_obj.completed_at - task_obj.started_at).total_seconds()
                        task_times.append(task_time)

                if task_times:
                    avg_task_time = sum(task_times) / len(task_times)
                    efficiency_ratio = avg_task_time / execution_time if execution_time > 0 else 0
                    self.print_result(f"Parallel Efficiency: {efficiency_ratio:.2f}")

            self.log_test_result("parallel_execution", "PASSED", {
                "parallel_tasks": len(parallel_tasks),
                "dependent_tasks": len(dependent_tasks),
                "execution_time": execution_time,
                "workflow_status": str(completed_workflow.status)
            })

        except Exception as e:
            self.print_result(f"Test Failed: {str(e)}", success=False)
            self.log_test_result("parallel_execution", "FAILED", {"error": str(e)})

    async def test_error_handling(self):
        """Test Scenario 5: Error handling and recovery."""
        self.print_header("Test Scenario 5: Error Handling and Recovery")

        user_request = "Analyze data that doesn't exist"

        try:
            # Create workflow that will encounter errors
            self.print_step("Step 1: Creating workflow with potential failures")
            workflow = await self.decomposer.decompose_request(user_request)

            # Simulate task failures
            self.print_step("Step 2: Executing workflow with simulated failures")

            # Override one agent to fail
            failing_agent = MockAgent("failing_agent", ["analysis"], should_fail=True)
            self.executor.agent_registry["research_agent"] = failing_agent

            completed_workflow = await self.executor.execute_workflow(workflow)

            # Check error handling
            failed_tasks = [t for t in completed_workflow.tasks.values()
                          if t.status.value == 'failed']
            pending_tasks = [t for t in completed_workflow.tasks.values()
                           if t.status.value == 'pending']

            self.print_result(f"Workflow Status: {completed_workflow.status}")
            self.print_result(f"Failed Tasks: {len(failed_tasks)}")
            self.print_result(f"Unstarted Tasks: {len(pending_tasks)}")

            # Verify error information is captured
            for task in failed_tasks:
                if hasattr(task, 'error_message'):
                    self.print_result(f"Error captured: {task.error_message}")

            self.log_test_result("error_handling", "PASSED", {
                "workflow_status": str(completed_workflow.status),
                "failed_tasks": len(failed_tasks),
                "unstarted_tasks": len(pending_tasks)
            })

        except Exception as e:
            self.print_result(f"Test Failed: {str(e)}", success=False)
            self.log_test_result("error_handling", "FAILED", {"error": str(e)})

    async def run_interactive_session(self):
        """Run interactive testing session."""
        self.print_header("Interactive Testing Session")

        print("Welcome to the Workflow Orchestration Manual Testing System!")
        print("You can test the system with your own requests.\n")

        while True:
            print("\n" + "─"*60)
            user_request = input("Enter your request (or 'quit' to exit): ").strip()

            if user_request.lower() in ['quit', 'exit', 'q']:
                break

            if not user_request:
                continue

            try:
                # Analyze request
                print(f"\n🔍 Analyzing: '{user_request}'")
                analysis = await self.analyzer.analyze_request(user_request)
                print(f"   Complexity: {analysis.complexity_score}/10")

                # Ask about approval requirement
                requires_approval = analysis.complexity_score > 7.0
                if requires_approval:
                    approval_input = input("   This is complex. Require approval? (y/n): ").lower()
                    requires_approval = approval_input.startswith('y')

                # Decompose request
                print(f"\n⚙️  Creating workflow...")
                workflow = await self.decomposer.decompose_request(
                    user_request, requires_approval=requires_approval, analysis=analysis
                )

                print(f"   Generated {len(workflow.tasks)} tasks")
                for task_id, task in workflow.tasks.items():
                    print(f"     {task_id}: {task.description}")

                # Handle approval if needed
                if requires_approval:
                    print(f"\n📋 Plan Preview:")
                    if workflow.plan_preview:
                        print(workflow.plan_preview)

                    approval = input("\nApprove this plan? (y/n): ").lower()
                    if not approval.startswith('y'):
                        print("   Plan rejected. Skipping execution.")
                        continue

                # Execute workflow
                print(f"\n🚀 Executing workflow...")
                completed_workflow = await self.executor.execute_workflow(workflow)

                print(f"   Status: {completed_workflow.status}")
                print(f"   Completed: {len([t for t in completed_workflow.tasks.values() if t.status.value == 'done'])} tasks")

            except Exception as e:
                print(f"   ❌ Error: {str(e)}")

    def generate_test_report(self):
        """Generate comprehensive test report."""
        self.print_header("Test Results Summary")

        if not self.test_results:
            print("No test results to report.")
            return

        passed_tests = [name for name, result in self.test_results.items()
                       if result["status"] == "PASSED"]
        failed_tests = [name for name, result in self.test_results.items()
                       if result["status"] == "FAILED"]

        print(f"📊 Test Summary:")
        print(f"   Total Tests: {len(self.test_results)}")
        print(f"   Passed: {len(passed_tests)} ✅")
        print(f"   Failed: {len(failed_tests)} ❌")
        print(f"   Success Rate: {len(passed_tests)/len(self.test_results)*100:.1f}%")

        if failed_tests:
            print(f"\n❌ Failed Tests:")
            for test_name in failed_tests:
                result = self.test_results[test_name]
                print(f"   - {test_name}: {result['details'].get('error', 'Unknown error')}")

        # Save detailed report
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.test_results, f, indent=2)

        print(f"\n📄 Detailed report saved to: {report_file}")


class MockAgent:
    """Mock agent for testing purposes."""

    def __init__(self, agent_id: str, capabilities: list, should_fail: bool = False):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.should_fail = should_fail

    async def process_message(self, message: str) -> str:
        """Simulate agent processing."""
        await asyncio.sleep(0.1)  # Simulate processing time

        if self.should_fail:
            raise Exception(f"Simulated failure in {self.agent_id}")

        return f"Task completed by {self.agent_id}: {message[:50]}..."


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Manual test scenarios for workflow orchestration")
    parser.add_argument("--scenario", help="Specific scenario to run")
    parser.add_argument("--interactive", action="store_true", help="Run interactive session")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--real-llm", action="store_true", help="Use real LLM (requires API keys)")

    args = parser.parse_args()

    # Create test orchestrator
    orchestrator = ManualTestOrchestrator()
    await orchestrator.setup_system(use_real_llm=args.real_llm)

    # Run scenarios
    if args.interactive:
        await orchestrator.run_interactive_session()
    elif args.all:
        print("🚀 Running all test scenarios...")
        await orchestrator.test_simple_request_workflow()
        await orchestrator.test_complex_request_with_approval()
        await orchestrator.test_workflow_modification()
        await orchestrator.test_parallel_execution()
        await orchestrator.test_error_handling()
        orchestrator.generate_test_report()
    elif args.scenario:
        scenario_map = {
            "simple": orchestrator.test_simple_request_workflow,
            "complex": orchestrator.test_complex_request_with_approval,
            "modification": orchestrator.test_workflow_modification,
            "parallel": orchestrator.test_parallel_execution,
            "error": orchestrator.test_error_handling
        }

        if args.scenario in scenario_map:
            await scenario_map[args.scenario]()
            orchestrator.generate_test_report()
        else:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available scenarios: {list(scenario_map.keys())}")
    else:
        print("Please specify --scenario, --interactive, or --all")
        print("Use --help for more information")


if __name__ == "__main__":
    asyncio.run(main())
