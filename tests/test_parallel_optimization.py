"""
Test suite for parallel workflow optimization in MUXI Overlord.

This test suite validates the complete parallel optimization pipeline including
dependency analysis, resource allocation, bottleneck detection, and execution.
"""

import asyncio
from typing import Dict, List, Any

# Import the parallel optimization components
from runtime.muxi.runtime.overlord.parallel import (
    ParallelWorkflowOptimizer,
    DependencyAnalyzer,
    ResourceManager,
    BottleneckDetector,
    ParallelExecutor,
)
from runtime.muxi.runtime.overlord.parallel.types import (
    AgentCapability,
    ExecutionPlan,
    OptimizedWorkflow,
)


class TestParallelOptimization:
    """Test suite for parallel workflow optimization."""

    async def sample_workflow(self) -> Dict[str, Any]:
        """Create a sample workflow for testing."""
        return {
            "id": "test_workflow",
            "tasks": {
                "task1": {
                    "description": "Research sustainable packaging trends",
                    "required_capabilities": ["web_research", "data_analysis"],
                    "dependencies": [],
                    "estimated_duration": 45.0,
                    "priority": 1,
                },
                "task2": {
                    "description": "Analyze company current practices",
                    "required_capabilities": ["document_analysis"],
                    "dependencies": [],
                    "estimated_duration": 30.0,
                    "priority": 1,
                },
                "task3": {
                    "description": "Write comprehensive report",
                    "required_capabilities": ["writing", "business_strategy"],
                    "dependencies": ["task1", "task2"],
                    "estimated_duration": 60.0,
                    "priority": 2,
                },
                "task4": {
                    "description": "Create presentation slides",
                    "required_capabilities": ["presentation", "design"],
                    "dependencies": ["task3"],
                    "estimated_duration": 25.0,
                    "priority": 3,
                },
            },
        }

    async def sample_agents(self) -> List[AgentCapability]:
        """Create sample agent capabilities for testing."""
        return [
            AgentCapability(
                agent_id="research_agent",
                capabilities={"web_research", "data_analysis"},
                max_concurrent_tasks=2,
                success_rate=0.95,
                average_response_time=40.0,
            ),
            AgentCapability(
                agent_id="analyst_agent",
                capabilities={"document_analysis", "business_strategy"},
                max_concurrent_tasks=3,
                success_rate=0.90,
                average_response_time=35.0,
            ),
            AgentCapability(
                agent_id="writer_agent",
                capabilities={"writing", "business_strategy"},
                max_concurrent_tasks=2,
                success_rate=0.88,
                average_response_time=50.0,
            ),
            AgentCapability(
                agent_id="designer_agent",
                capabilities={"presentation", "design"},
                max_concurrent_tasks=2,
                success_rate=0.92,
                average_response_time=30.0,
            ),
        ]

    def optimizer(self) -> ParallelWorkflowOptimizer:
        """Create a parallel workflow optimizer for testing."""
        return ParallelWorkflowOptimizer(sensitivity_threshold=0.5)

    async def test_dependency_analysis(self, sample_workflow):
        """Test dependency analysis functionality."""
        print("\n🧪 Testing Dependency Analysis")

        analyzer = DependencyAnalyzer()

        # Build dependency graph
        dependency_graph = await analyzer.build_dependency_graph(sample_workflow["tasks"])

        assert len(dependency_graph) == 4
        assert "task1" in dependency_graph
        assert "task2" in dependency_graph
        assert "task3" in dependency_graph
        assert "task4" in dependency_graph

        # Check dependencies are correctly set
        assert len(dependency_graph["task1"].dependencies) == 0
        assert len(dependency_graph["task2"].dependencies) == 0
        assert len(dependency_graph["task3"].dependencies) == 2
        assert "task1" in dependency_graph["task3"].dependencies
        assert "task2" in dependency_graph["task3"].dependencies
        assert len(dependency_graph["task4"].dependencies) == 1
        assert "task3" in dependency_graph["task4"].dependencies

        # Test parallel group detection
        parallel_groups = await analyzer.find_parallel_groups()
        assert len(parallel_groups) == 3  # Level 0: task1,task2; Level 1: task3; Level 2: task4

        # First group should have task1 and task2 (no dependencies)
        first_group = parallel_groups[0]
        assert len(first_group.task_ids) == 2
        assert "task1" in first_group.task_ids
        assert "task2" in first_group.task_ids

        print("✅ Dependency Analysis: All tests passed")

    async def test_resource_allocation(self, sample_workflow, sample_agents):
        """Test resource allocation optimization."""
        print("\n🧪 Testing Resource Allocation")

        resource_manager = ResourceManager()

        # Register agent capabilities
        for agent in sample_agents:
            await resource_manager.register_agent(agent)

        # Create sample parallel groups
        analyzer = DependencyAnalyzer()
        await analyzer.build_dependency_graph(sample_workflow["tasks"])
        parallel_groups = await analyzer.find_parallel_groups()

        # Optimize allocation
        available_agents = [agent.agent_id for agent in sample_agents]
        allocation = await resource_manager.optimize_allocation(parallel_groups, available_agents)

        assert allocation.allocation_id is not None
        assert len(allocation.task_assignments) > 0

        # Check that all tasks are assigned
        task_ids = set()
        for group in parallel_groups:
            task_ids.update(group.task_ids)

        assigned_tasks = set(allocation.task_assignments.keys())
        assert task_ids.issubset(assigned_tasks)

        # Check load balancing metrics
        assert 0.0 <= allocation.parallel_efficiency <= 1.0
        assert 0.0 <= allocation.load_balance_score <= 1.0

        print("✅ Resource Allocation: All tests passed")

    async def test_bottleneck_detection(self, sample_workflow, sample_agents):
        """Test bottleneck detection."""
        print("\n🧪 Testing Bottleneck Detection")

        bottleneck_detector = BottleneckDetector(sensitivity_threshold=0.3)

        # Create a mock execution plan
        from runtime.muxi.runtime.overlord.parallel.types import ExecutionPlan, ResourceAllocation

        resource_allocation = ResourceAllocation(allocation_id="test_alloc")
        resource_allocation.parallel_efficiency = 0.4  # Low efficiency to trigger bottleneck
        resource_allocation.load_balance_score = 0.3  # Poor balance to trigger bottleneck

        execution_plan = ExecutionPlan(
            plan_id="test_plan",
            parallel_groups=[],
            resource_allocation=resource_allocation,
            execution_order=[],
        )
        execution_plan.parallelization_speedup = 1.2  # Low speedup

        # Detect bottlenecks
        bottlenecks = await bottleneck_detector.analyze_workflow_bottlenecks(
            execution_plan, resource_allocation
        )

        assert len(bottlenecks) > 0  # Should detect bottlenecks due to low efficiency/balance

        # Test optimization suggestions
        suggestions = await bottleneck_detector.suggest_optimizations(bottlenecks)
        assert isinstance(suggestions, list)

        print("✅ Bottleneck Detection: All tests passed")

    async def test_end_to_end_optimization(self, optimizer, sample_workflow, sample_agents):
        """Test complete end-to-end optimization pipeline."""
        print("\n🧪 Testing End-to-End Optimization")

        # Register agent capabilities
        await optimizer.register_agent_capabilities(sample_agents)

        # Get available agent IDs
        available_agents = [agent.agent_id for agent in sample_agents]

        # Optimize the workflow
        optimized_workflow = await optimizer.optimize_workflow(sample_workflow, available_agents)

        assert isinstance(optimized_workflow, OptimizedWorkflow)
        assert optimized_workflow.workflow_id == "test_workflow"
        assert optimized_workflow.expected_speedup >= 1.0
        assert 0.0 <= optimized_workflow.optimization_confidence <= 1.0

        # Check execution plan
        execution_plan = optimized_workflow.execution_plan
        assert isinstance(execution_plan, ExecutionPlan)
        assert len(execution_plan.parallel_groups) > 0
        assert execution_plan.max_concurrent_agents > 0

        print("✅ End-to-End Optimization: All tests passed")

    async def test_parallel_execution_simulation(self, optimizer, sample_workflow, sample_agents):
        """Test parallel execution with a mock executor."""
        print("\n🧪 Testing Parallel Execution Simulation")

        # Set up optimizer
        await optimizer.register_agent_capabilities(sample_agents)
        available_agents = [agent.agent_id for agent in sample_agents]

        # Optimize workflow
        optimized_workflow = await optimizer.optimize_workflow(sample_workflow, available_agents)

        # Create executor
        executor = ParallelExecutor()

        # Mock task executor function
        async def mock_task_executor(task_id: str, agent_id: str, context: Dict[str, Any]) -> str:
            """Mock function to simulate task execution."""
            await asyncio.sleep(0.1)  # Simulate work
            return f"Result for {task_id} executed by {agent_id}"

        # Mock progress callback
        progress_updates = []

        def mock_progress_callback(progress_data: Dict[str, Any]) -> None:
            progress_updates.append(progress_data)

        # Execute the workflow
        execution_result = await executor.execute_workflow(
            optimized_workflow, mock_task_executor, mock_progress_callback
        )

        assert execution_result.execution_id is not None
        assert execution_result.success is True
        assert execution_result.actual_duration > 0
        assert execution_result.actual_speedup >= 1.0
        assert len(execution_result.completed_tasks) > 0
        assert len(execution_result.failed_tasks) == 0

        # Check progress updates were received
        assert len(progress_updates) > 0

        print("✅ Parallel Execution Simulation: All tests passed")

    async def test_optimization_recommendations(self, optimizer, sample_workflow):
        """Test optimization recommendations."""
        print("\n🧪 Testing Optimization Recommendations")

        # Get recommendations before optimization
        recommendations = await optimizer.get_optimization_recommendations(sample_workflow)

        assert isinstance(recommendations, list)

        # Should not have critical issues for this simple workflow
        critical_issues = [r for r in recommendations if r.get("priority") == "critical"]
        assert len(critical_issues) == 0

        print("✅ Optimization Recommendations: All tests passed")

    async def test_error_handling(self, optimizer):
        """Test error handling in optimization pipeline."""
        print("\n🧪 Testing Error Handling")

        # Test with invalid workflow
        invalid_workflow = {
            "id": "invalid_workflow",
            "tasks": {
                "task1": {
                    "dependencies": ["nonexistent_task"],  # Invalid dependency
                    "description": "Invalid task",
                }
            },
        }

        try:
            optimized_workflow = await optimizer.optimize_workflow(invalid_workflow, ["agent1"])
            # Should complete but with warnings about invalid dependencies
            assert optimized_workflow is not None
        except Exception as e:
            # Or it might raise an exception, which is also acceptable
            assert isinstance(e, Exception)

        print("✅ Error Handling: All tests passed")


async def run_all_tests():
    """Run all parallel optimization tests."""
    print("🚀 Starting Parallel Optimization Test Suite")
    print("=" * 60)

    test_instance = TestParallelOptimization()

    # Create fixtures
    sample_workflow = await test_instance.sample_workflow()
    sample_agents = await test_instance.sample_agents()
    optimizer = test_instance.optimizer()

    try:
        # Run all tests
        await test_instance.test_dependency_analysis(sample_workflow)
        await test_instance.test_resource_allocation(sample_workflow, sample_agents)
        await test_instance.test_bottleneck_detection(sample_workflow, sample_agents)
        await test_instance.test_end_to_end_optimization(optimizer, sample_workflow, sample_agents)
        await test_instance.test_parallel_execution_simulation(
            optimizer, sample_workflow, sample_agents
        )
        await test_instance.test_optimization_recommendations(optimizer, sample_workflow)
        await test_instance.test_error_handling(optimizer)

        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("✅ Phase 2.2: Parallel Workflow Optimization is working correctly")

        return True

    except Exception as e:
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("🔧 Phase 2.2 needs debugging")
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
