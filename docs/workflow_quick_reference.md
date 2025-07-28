# MUXI Workflow System - Quick Reference

## Configuration Quick Setup

### Basic Configuration
```yaml
# formation.yaml
overlord:
  config:
    auto_decomposition: true
    complexity_threshold: 7.0
    plan_approval_threshold: 10
    
    workflow:
      complexity_method: "heuristic"
      routing_strategy: "capability_based"
      error_recovery: "retry_with_backoff"
      
      retry:
        max_attempts: 3
        initial_delay: 1.0
        backoff_factor: 2.0
      
      timeouts:
        task_timeout: 300
        workflow_timeout: 3600
```

### Advanced Configuration
```yaml
overlord:
  config:
    workflow:
      # Custom routing rules
      routing_rules:
        - pattern: "code review"
          agents: ["senior-dev", "code-expert"]
          weight: 0.9
          
      # Workflow overrides
      overrides:
        - pattern: "research"
          priority: 10
          config:
            complexity_threshold: 5.0
            max_parallel_tasks: 10
```

## API Reference

### Chat with Workflow Support
```python
# Simple request (no workflow)
response = await overlord.chat(
    "What's the weather?",
    user_id="user123",
    session_id="session456"
)

# Complex request (triggers workflow)
response = await overlord.chat(
    "Research AI trends, create report, and schedule meeting",
    user_id="user123",
    session_id="session456"
)

# Check if workflow was triggered
workflow_id = response.metadata.get('workflow_id') if hasattr(response, 'metadata') else None
```

### Workflow Status Operations
```python
# Get workflow status
status = await overlord.get_workflow_status(workflow_id)
print(f"Status: {status.status}, Progress: {status.progress_percent}%")

# List active workflows
active_workflows = await overlord.list_workflows(status="active", limit=10)

# Get workflow metrics
metrics = await overlord.get_workflow_metrics()
print(f"Total workflows: {metrics['total_workflows']}")

# Cancel workflow
await overlord.cancel_workflow(workflow_id)
```

### Direct Workflow Execution
```python
# Create workflow manually
workflow = Workflow(
    id=generate_workflow_id(),
    tasks=[
        Task(id="task1", type="research", agent_requirements=["researcher"]),
        Task(id="task2", type="writing", agent_requirements=["writer"], dependencies=["task1"])
    ]
)

# Execute workflow
result = await overlord.execute_workflow(workflow)
```

## Common Patterns

### Research & Report Generation
```python
prompt = """
Research the latest developments in quantum computing, 
analyze the market implications, 
create a comprehensive report, 
and save it as a PDF document
"""

response = await overlord.chat(prompt, user_id="analyst", session_id="research_session")
```

### Data Analysis Pipeline
```python
prompt = """
Load the sales data from Q3 2024,
perform statistical analysis to identify trends,
create visualizations showing key metrics,
generate executive summary,
and email the report to the leadership team
"""

response = await overlord.chat(prompt, user_id="data_analyst", session_id="analysis_session")
```

### Multi-Platform Content Creation
```python
prompt = """
Write a blog post about sustainable energy trends,
create social media posts for Twitter and LinkedIn,
generate accompanying graphics,
schedule posts for optimal engagement times,
and track performance metrics
"""

response = await overlord.chat(prompt, user_id="content_manager", session_id="content_session")
```

## Complexity Triggers

### High Complexity Patterns (Score 8-10)
- Multi-step processes with dependencies
- Research + analysis + output generation
- Cross-platform operations
- Data processing pipelines
- Content creation + distribution

### Medium Complexity Patterns (Score 5-7)
- Simple research tasks
- Basic content creation
- Single-tool operations with context
- Straightforward analysis tasks

### Low Complexity Patterns (Score 1-4)
- Simple questions
- Single-step operations
- Basic information retrieval
- Direct tool usage

## Debugging Workflows

### Check Workflow Configuration
```python
print(f"Auto decomposition: {overlord.auto_decomposition}")
print(f"Complexity threshold: {overlord.workflow_config.complexity_threshold}")
print(f"Routing strategy: {overlord.workflow_config.routing_strategy}")
```

### Test Complexity Analysis
```python
analysis = await overlord.request_analyzer.analyze_request(prompt)
print(f"Complexity score: {analysis.complexity_score}")
print(f"Requires decomposition: {analysis.requires_decomposition}")
print(f"Reasoning: {analysis.reasoning}")
```

### Monitor Workflow Execution
```python
async def monitor_workflow(workflow_id: str):
    while True:
        status = await overlord.get_workflow_status(workflow_id)
        print(f"Workflow {workflow_id}: {status.status} ({status.progress_percent}%)")
        
        if status.status in ['completed', 'failed', 'cancelled']:
            break
            
        await asyncio.sleep(2)
```

### Debug Agent Selection
```python
# Check available agents
for agent in overlord.agents:
    print(f"Agent {agent.id}: capabilities={agent.capabilities}")

# Test agent routing
task = Task(id="test", type="research", agent_requirements=["research", "web_search"])
selected_agent = overlord.workflow_executor.agent_selector.select_agent(
    task, TaskRoutingStrategy.CAPABILITY_BASED
)
print(f"Selected agent: {selected_agent.id}")
```

## Error Handling

### Common Error Patterns
```python
try:
    response = await overlord.chat(complex_prompt, user_id="user", session_id="session")
except WorkflowTimeoutError as e:
    print(f"Workflow timed out: {e}")
except WorkflowExecutionError as e:
    print(f"Workflow execution failed: {e}")
except ComplexityAnalysisError as e:
    print(f"Failed to analyze request complexity: {e}")
```

### Workflow Error Recovery
```python
# Check for failed tasks
workflow = await overlord.get_workflow_status(workflow_id)
if workflow.status == WorkflowStatus.FAILED:
    failed_tasks = [task for task in workflow.tasks if task.status == TaskStatus.FAILED]
    print(f"Failed tasks: {[task.id for task in failed_tasks]}")
    
    # Retry failed tasks
    for task in failed_tasks:
        await overlord.retry_task(workflow_id, task.id)
```

## Performance Optimization

### Reduce Workflow Overhead
```yaml
overlord:
  config:
    workflow:
      # Increase complexity threshold to reduce workflow triggers
      complexity_threshold: 8.0
      
      # Optimize parallel execution
      max_parallel_tasks: 5
      
      # Enable caching
      enable_caching: true
      cache_ttl: 3600
```

### Monitor Performance
```python
# Get workflow metrics
metrics = await overlord.get_workflow_metrics()
print(f"Average execution time: {metrics['average_execution_time']}s")
print(f"Success rate: {metrics['success_rate']}%")
print(f"Active workflows: {metrics['in_progress_workflows']}")

# Monitor resource usage
print(f"Agent utilization: {metrics['agent_utilization']}")
print(f"Memory usage: {metrics['memory_usage_mb']}MB")
```

## Testing Workflows

### Unit Testing
```python
import pytest
from muxi.formation.workflow import WorkflowExecutor, Task

@pytest.mark.asyncio
async def test_simple_workflow():
    executor = WorkflowExecutor()
    
    task = Task(
        id="test_task",
        type="simple_test",
        description="Test task",
        agent_requirements=["test_agent"]
    )
    
    result = await executor.execute_single_task(task, create_test_context())
    assert result.status == TaskStatus.COMPLETED
```

### Integration Testing
```python
@pytest.mark.asyncio
async def test_workflow_integration():
    formation = await create_test_formation()
    overlord = await formation.start_overlord()
    
    # Test complex request
    response = await overlord.chat(
        "Test complex workflow request",
        user_id="test_user",
        session_id="test_session"
    )
    
    # Verify workflow execution
    assert hasattr(response, 'metadata')
    assert response.metadata.get('workflow_id') is not None
    
    await formation.stop_overlord()
```

## Configuration Examples

### Research-Heavy Workloads
```yaml
overlord:
  config:
    workflow:
      complexity_threshold: 5.0  # Lower threshold for research tasks
      routing_strategy: "capability_based"
      
      overrides:
        - pattern: "research"
          config:
            max_parallel_tasks: 8
            task_timeout: 600
            
      routing_rules:
        - pattern: "academic research"
          agents: ["research-specialist", "academic-agent"]
          weight: 1.0
```

### High-Performance Setup
```yaml
overlord:
  config:
    workflow:
      max_parallel_tasks: 10
      max_concurrent_workflows: 20
      
      retry:
        max_attempts: 5
        initial_delay: 0.5
        
      timeouts:
        task_timeout: 180
        enable_adaptive_timeout: true
```

### Development/Testing Setup
```yaml
overlord:
  config:
    workflow:
      complexity_threshold: 3.0  # Lower threshold for testing
      error_recovery: "fail_fast"  # Immediate failure for debugging
      
      retry:
        max_attempts: 1  # No retries during development
        
      debug_logging: true
      log_level: "DEBUG"
```

## Troubleshooting Checklist

### Workflows Not Triggering
- [ ] Check `auto_decomposition: true`
- [ ] Verify `complexity_threshold` setting
- [ ] Test complexity analysis manually
- [ ] Ensure no explicit agent specified
- [ ] Check for clarification responses

### Poor Performance
- [ ] Monitor `max_parallel_tasks` setting
- [ ] Check agent utilization metrics
- [ ] Review workflow history cleanup
- [ ] Verify caching configuration
- [ ] Monitor memory usage

### High Failure Rate
- [ ] Review retry configuration
- [ ] Check agent capabilities alignment
- [ ] Monitor timeout settings
- [ ] Review error patterns in metrics
- [ ] Verify MCP tool availability

### Agent Selection Issues
- [ ] Verify agent capabilities
- [ ] Check routing strategy configuration
- [ ] Review custom routing rules
- [ ] Monitor agent load balancing
- [ ] Test agent selection manually