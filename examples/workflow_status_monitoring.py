"""
Example: Workflow Status Monitoring

This example demonstrates how to use the workflow status endpoints
to monitor and manage workflows in MUXI Runtime.
"""

import asyncio

from muxi.formation.overlord.overlord import Overlord
from muxi.datatypes.workflow import WorkflowStatus


async def monitor_workflow_execution(overlord: Overlord, user_id: str):
    """
    Example of monitoring workflow execution using status endpoints.
    """
    print("=== Workflow Status Monitoring Example ===\n")

    # 1. Submit a complex request that triggers workflow
    message = """
    Please analyze the latest sales data, create a comprehensive report
    with visualizations, and then draft an executive summary email.
    """

    print(f"Submitting request: {message[:50]}...\n")

    # Start workflow execution in background
    task = asyncio.create_task(overlord.chat(user_id=user_id, message=message, use_async=True))

    # Give it a moment to start
    await asyncio.sleep(1)

    # 2. Get active workflows
    active_ids = overlord.get_active_workflow_ids()
    print(f"Active workflows: {len(active_ids)}")

    if active_ids:
        workflow_id = active_ids[0]
        print(f"Monitoring workflow: {workflow_id}\n")

        # 3. Monitor workflow progress
        completed = False
        while not completed:
            workflow = overlord.get_workflow_status(workflow_id)

            if workflow:
                print(f"Status: {workflow.status}")
                print(f"Progress: {workflow.progress_percent:.1f}%")
                print(f"Current phase: {workflow.current_phase}/{workflow.total_phases}")

                # Check task statuses
                task_summary = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}

                for task in workflow.tasks.values():
                    if task.status.value == "pending":
                        task_summary["pending"] += 1
                    elif task.status.value == "in_progress":
                        task_summary["in_progress"] += 1
                    elif task.status.value in ["done", "completed"]:
                        task_summary["completed"] += 1
                    elif task.status.value == "failed":
                        task_summary["failed"] += 1

                print(f"Tasks: {task_summary}")
                print("-" * 40)

                # Check if completed
                if workflow.is_complete:
                    completed = True
                    print(f"\nWorkflow completed with status: {workflow.status}")
                else:
                    await asyncio.sleep(2)  # Check every 2 seconds
            else:
                print("Workflow no longer active")
                completed = True

    # Wait for the original task to complete
    try:
        result = await task
        print(f"\nFinal result: {result[:100]}...")
    except Exception as e:
        print(f"\nError: {e}")


async def demonstrate_workflow_management(overlord: Overlord):
    """
    Demonstrate workflow management capabilities.
    """
    print("\n\n=== Workflow Management Demo ===\n")

    # 1. List all workflows
    print("1. Listing all workflows:")
    all_workflows = overlord.list_workflows()
    print(f"   Total workflows: {len(all_workflows)}")

    # 2. Filter by user
    print("\n2. Filter workflows by user:")
    user_workflows = overlord.list_workflows(user_id="demo-user")
    print(f"   Workflows for 'demo-user': {len(user_workflows)}")

    # 3. Filter by status
    print("\n3. Filter by status:")
    completed = overlord.list_workflows(status=WorkflowStatus.COMPLETED)
    in_progress = overlord.list_workflows(status=WorkflowStatus.IN_PROGRESS)
    failed = overlord.list_workflows(status=WorkflowStatus.FAILED)

    print(f"   Completed: {len(completed)}")
    print(f"   In Progress: {len(in_progress)}")
    print(f"   Failed: {len(failed)}")

    # 4. Get workflow metrics
    print("\n4. Workflow Metrics:")
    metrics = overlord.get_workflow_metrics()
    for key, value in metrics.items():
        print(f"   {key}: {value}")

    # 5. Demonstrate cancellation (if there's an active workflow)
    active_ids = overlord.get_active_workflow_ids()
    if active_ids:
        print(f"\n5. Cancelling workflow: {active_ids[0]}")
        cancelled = await overlord.cancel_workflow(active_ids[0])
        print(f"   Cancellation result: {cancelled}")

    # 6. Clean up old workflows
    print("\n6. Cleaning up old workflows (>30 days):")
    cleared = overlord.clear_workflow_history(older_than_days=30)
    print(f"   Cleared {cleared} old workflows")


async def main():
    """
    Main demonstration function.
    """
    # Initialize Overlord with workflow support
    overlord = Overlord(
        enable_workflow_by_default=True, complexity_threshold=5.0  # Lower threshold for demo
    )

    # You would normally load a formation here
    # await overlord.load_formation_from_path("formation.afs")

    # For demo purposes, create a mock agent
    from unittest.mock import Mock, AsyncMock

    mock_agent = Mock()
    mock_agent.agent_id = "demo-agent"
    mock_agent.process_message = AsyncMock(return_value="Task completed successfully")
    overlord.agents = {"demo-agent": mock_agent}

    try:
        # Run monitoring example
        await monitor_workflow_execution(overlord, "demo-user")

        # Run management demo
        await demonstrate_workflow_management(overlord)

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\nError in demo: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
