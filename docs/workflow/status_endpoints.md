# Workflow Status Endpoints Documentation

## Overview

The MUXI Runtime now includes comprehensive workflow status endpoints and monitoring capabilities (Phase 2, Stream 2). These features enable real-time tracking of workflow execution, historical analysis, and workflow management.

## Implemented Features

### 1. Workflow History Tracking

All workflows are now automatically tracked in a persistent history after execution:

- **Active Workflows**: Currently executing workflows stored in `self.active_workflows`
- **Pending Approvals**: Workflows awaiting user approval in `self.pending_approvals`
- **Workflow History**: Completed/failed/cancelled workflows in `self.workflow_history`

### 2. Status Query Methods

#### `get_workflow_status(workflow_id: str) -> Optional[Workflow]`
Retrieve the current status of any workflow by ID. Checks active workflows, history, and pending approvals.

```python
workflow = overlord.get_workflow_status("wrk_abc123")
if workflow:
    print(f"Status: {workflow.status}")
    print(f"Progress: {workflow.progress_percent}%")
```

#### `list_workflows(user_id=None, status=None, limit=100, offset=0) -> List[Workflow]`
List workflows with flexible filtering options:

```python
# Get all workflows for a user
user_workflows = overlord.list_workflows(user_id="user123")

# Get only completed workflows
completed = overlord.list_workflows(status=WorkflowStatus.COMPLETED)

# Paginate results
page2 = overlord.list_workflows(limit=50, offset=50)
```

#### `get_active_workflow_ids() -> List[str]`
Get IDs of all currently active workflows for quick status checks.

### 3. Workflow Management

#### `cancel_workflow(workflow_id: str) -> bool`
Cancel an active workflow and move it to history:

```python
success = await overlord.cancel_workflow("wrk_abc123")
if success:
    print("Workflow cancelled successfully")
```

Features:
- Thread-safe cancellation with proper locking
- Automatic status update to CANCELLED
- Moves workflow to history for audit trail
- Updates cancellation metrics

### 4. Workflow Metrics

#### `get_workflow_metrics() -> Dict[str, Any]`
Get comprehensive workflow execution metrics:

```python
metrics = overlord.get_workflow_metrics()
# Returns:
# {
#     "total_workflows": 150,
#     "successful_workflows": 120,
#     "failed_workflows": 20,
#     "cancelled_workflows": 10,
#     "in_progress_workflows": 5,
#     "pending_approval_workflows": 2,
#     "success_rate": 85.71,
#     "average_execution_time_seconds": 45.3,
#     "workflow_count_by_user": {"user1": 50, "user2": 100}
# }
```

### 5. History Management

#### `clear_workflow_history(older_than_days: int = 30) -> int`
Clean up old workflows from history to manage storage:

```python
cleared = overlord.clear_workflow_history(older_than_days=30)
print(f"Cleared {cleared} old workflows")
```

## Thread Safety

All workflow data access is protected by `self._workflow_lock` to ensure thread-safe operations in concurrent environments:

- Workflow creation and tracking
- Status updates and transitions
- History movements
- Metrics updates

## Automatic Tracking

Workflows are automatically tracked throughout their lifecycle:

1. **Creation**: Metrics updated when workflow is created
2. **Execution**: Progress tracked in active workflows
3. **Completion**: Moved to history with final metrics
4. **Error Handling**: Failed workflows tracked with error details

## Integration with WorkflowExecutor

The WorkflowExecutor has been enhanced with:

- Cancellation checking during phase execution
- Proper status determination for cancelled workflows
- Existing `cancel_workflow()` method for immediate cancellation

## Usage Example

```python
from muxi.formation.overlord.overlord import Overlord

# Initialize with workflow support
overlord = Overlord(enable_workflow_by_default=True)
await overlord.load_formation_from_path("formation.afs")

# Submit a complex request
response = await overlord.chat(
    user_id="user123",
    message="Analyze data and create report",
    use_async=True
)

# Monitor execution
active_ids = overlord.get_active_workflow_ids()
if active_ids:
    workflow_id = active_ids[0]

    # Check status periodically
    while True:
        workflow = overlord.get_workflow_status(workflow_id)
        if workflow and workflow.is_complete:
            break
        await asyncio.sleep(2)

# Get execution metrics
metrics = overlord.get_workflow_metrics()
print(f"Success rate: {metrics['success_rate']}%")

# List user's workflows
user_workflows = overlord.list_workflows(user_id="user123")
print(f"User has {len(user_workflows)} workflows")
```

## Testing

Comprehensive tests are provided in `tests/e1e/day_7/test_workflow_status_endpoints.py` covering:

- Status retrieval
- Workflow listing with filters
- Cancellation functionality
- Metrics tracking
- History management
- Thread safety

## Future Enhancements

While not implemented in this phase, potential future enhancements include:

1. **Workflow Export**: Export workflow history to external storage
2. **Real-time Notifications**: WebSocket/SSE updates for workflow progress
3. **Workflow Templates**: Save successful workflows as reusable templates
4. **Advanced Analytics**: Deeper insights into workflow performance
5. **Workflow Replay**: Re-execute historical workflows
