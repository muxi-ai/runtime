# MUXI Workflow System - Technical Implementation Guide

**For Developers & System Integrators**

## Core Implementation Details

### Task Decomposition Algorithm

The task decomposition process follows this algorithm:

```python
async def decompose_request(self, request: str, context: Dict = None) -> Workflow:
    """
    Decomposes a complex request into executable workflow tasks.
    
    Algorithm:
    1. Parse request into semantic components
    2. Identify required capabilities and tools
    3. Create task dependency graph
    4. Optimize task ordering for parallel execution
    5. Generate executable workflow object
    """
    
    # Phase 1: Semantic Analysis
    components = await self._parse_semantic_components(request)
    
    # Phase 2: Capability Mapping
    required_capabilities = self._identify_capabilities(components)
    
    # Phase 3: Task Creation
    tasks = []
    for component in components:
        task = Task(
            id=generate_task_id(),
            type=component.task_type,
            description=component.description,
            agent_requirements=component.required_capabilities,
            dependencies=self._calculate_dependencies(component, tasks),
            metadata=component.metadata
        )
        tasks.append(task)
    
    # Phase 4: Dependency Graph Optimization
    optimized_tasks = self._optimize_task_dependencies(tasks)
    
    # Phase 5: Workflow Generation
    workflow = Workflow(
        id=generate_workflow_id(),
        status=WorkflowStatus.PENDING,
        tasks=optimized_tasks,
        created_at=datetime.now(),
        metadata={
            "original_request": request,
            "complexity_score": context.get("complexity_score", 0),
            "estimated_duration": self._estimate_duration(optimized_tasks)
        }
    )
    
    return workflow
```

### Workflow Execution Engine

```python
class WorkflowExecutor:
    """
    Executes workflows with support for:
    - Parallel task execution
    - Error recovery strategies  
    - Resource management
    - Progress tracking
    """
    
    async def execute_workflow(self, workflow: Workflow) -> WorkflowResult:
        """Main execution loop with comprehensive error handling"""
        
        try:
            # Initialize execution context
            context = ExecutionContext(
                workflow_id=workflow.id,
                start_time=datetime.now(),
                resource_pool=self._create_resource_pool(),
                progress_tracker=self._create_progress_tracker(workflow)
            )
            
            # Execute workflow phases
            await self._execute_workflow_phases(workflow, context)
            
            # Finalize and return results
            return self._finalize_workflow_execution(workflow, context)
            
        except Exception as e:
            return await self._handle_workflow_error(workflow, e)
    
    async def _execute_workflow_phases(self, workflow: Workflow, context: ExecutionContext):
        """Execute workflow in phases based on task dependencies"""
        
        phases = self._calculate_execution_phases(workflow.tasks)
        
        for phase_num, phase_tasks in enumerate(phases):
            context.current_phase = phase_num
            
            # Execute tasks in current phase (parallel execution)
            phase_results = await self._execute_phase_tasks(phase_tasks, context)
            
            # Update workflow state
            workflow.completed_tasks.extend([
                task for task, result in phase_results.items() 
                if result.status == TaskStatus.COMPLETED
            ])
            
            # Check for phase failures
            failed_tasks = [
                task for task, result in phase_results.items()
                if result.status == TaskStatus.FAILED
            ]
            
            if failed_tasks:
                await self._handle_phase_failures(failed_tasks, workflow, context)
    
    async def _execute_phase_tasks(self, tasks: List[Task], context: ExecutionContext) -> Dict[Task, TaskResult]:
        """Execute tasks in parallel with resource management"""
        
        # Create semaphore for resource limiting
        semaphore = asyncio.Semaphore(self.config.max_parallel_tasks)
        
        async def execute_single_task(task: Task) -> Tuple[Task, TaskResult]:
            async with semaphore:
                return task, await self._execute_single_task(task, context)
        
        # Execute all phase tasks concurrently
        task_futures = [execute_single_task(task) for task in tasks]
        completed_tasks = await asyncio.gather(*task_futures, return_exceptions=True)
        
        # Process results and handle exceptions
        results = {}
        for result in completed_tasks:
            if isinstance(result, Exception):
                # Handle task execution exception
                task = self._extract_task_from_exception(result)
                results[task] = TaskResult(
                    status=TaskStatus.FAILED,
                    error=str(result),
                    timestamp=datetime.now()
                )
            else:
                task, task_result = result
                results[task] = task_result
        
        return results
```

### Agent Selection Algorithm

```python
class AgentSelector:
    """Intelligent agent selection with multiple strategies"""
    
    def select_agent(self, task: Task, strategy: TaskRoutingStrategy) -> Agent:
        """Select optimal agent based on routing strategy"""
        
        if strategy == TaskRoutingStrategy.CAPABILITY_BASED:
            return self._select_by_capability(task)
        elif strategy == TaskRoutingStrategy.LOAD_BALANCED:
            return self._select_by_load(task)
        elif strategy == TaskRoutingStrategy.AFFINITY_BASED:
            return self._select_by_affinity(task)
        else:
            return self._select_round_robin(task)
    
    def _select_by_capability(self, task: Task) -> Agent:
        """Select agent with best capability match"""
        
        scored_agents = []
        for agent in self.available_agents:
            # Calculate capability score
            capability_score = self._calculate_capability_score(task, agent)
            
            # Calculate experience score
            experience_score = self._calculate_experience_score(task, agent)
            
            # Calculate current load penalty
            load_penalty = self._calculate_load_penalty(agent)
            
            # Combined score
            total_score = (
                capability_score * 0.5 + 
                experience_score * 0.3 - 
                load_penalty * 0.2
            )
            
            scored_agents.append((agent, total_score))
        
        # Return agent with highest score
        return max(scored_agents, key=lambda x: x[1])[0]
    
    def _calculate_capability_score(self, task: Task, agent: Agent) -> float:
        """Calculate how well agent capabilities match task requirements"""
        
        required_caps = set(task.agent_requirements)
        agent_caps = set(agent.capabilities)
        
        if not required_caps.issubset(agent_caps):
            return 0.0  # Agent cannot handle this task
        
        # Calculate match quality
        exact_matches = len(required_caps.intersection(agent_caps))
        total_required = len(required_caps)
        
        return exact_matches / total_required if total_required > 0 else 1.0
```

### Error Recovery System

```python
class WorkflowErrorHandler:
    """Comprehensive error handling and recovery"""
    
    async def handle_task_error(self, task: Task, error: Exception, context: ExecutionContext) -> ErrorRecoveryResult:
        """Handle individual task errors with configurable strategies"""
        
        # Classify error type
        error_type = self._classify_error(error)
        
        # Get recovery strategy
        strategy = self._get_recovery_strategy(task, error_type)
        
        # Execute recovery strategy
        if strategy == ErrorRecoveryStrategy.RETRY_WITH_BACKOFF:
            return await self._retry_with_backoff(task, error, context)
        elif strategy == ErrorRecoveryStrategy.SKIP_AND_CONTINUE:
            return await self._skip_task(task, error, context)
        elif strategy == ErrorRecoveryStrategy.ESCALATE_TO_USER:
            return await self._escalate_to_user(task, error, context)
        else:  # FAIL_FAST
            return await self._fail_workflow(task, error, context)
    
    async def _retry_with_backoff(self, task: Task, error: Exception, context: ExecutionContext) -> ErrorRecoveryResult:
        """Implement exponential backoff retry logic"""
        
        retry_state = context.get_retry_state(task.id)
        
        if retry_state.attempt_count >= self.config.retry.max_attempts:
            return ErrorRecoveryResult(
                strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
                success=False,
                message=f"Task {task.id} failed after {retry_state.attempt_count} attempts"
            )
        
        # Calculate backoff delay
        delay = self.config.retry.initial_delay * (
            self.config.retry.backoff_factor ** retry_state.attempt_count
        )
        
        # Wait before retry
        await asyncio.sleep(delay)
        
        # Increment attempt count
        retry_state.attempt_count += 1
        
        # Retry task execution
        try:
            result = await self._execute_single_task(task, context)
            return ErrorRecoveryResult(
                strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
                success=True,
                result=result
            )
        except Exception as retry_error:
            # Recursive retry handling
            return await self.handle_task_error(task, retry_error, context)
    
    def _classify_error(self, error: Exception) -> ErrorType:
        """Classify errors for appropriate handling"""
        
        if isinstance(error, asyncio.TimeoutError):
            return ErrorType.TIMEOUT
        elif isinstance(error, ConnectionError):
            return ErrorType.NETWORK
        elif isinstance(error, PermissionError):
            return ErrorType.AUTHORIZATION
        elif "rate limit" in str(error).lower():
            return ErrorType.RATE_LIMIT
        else:
            return ErrorType.UNKNOWN
```

### Workflow State Management

```python
class WorkflowManager:
    """Centralized workflow state and lifecycle management"""
    
    def __init__(self):
        self.active_workflows: Dict[str, Workflow] = {}
        self.workflow_history: Dict[str, Workflow] = {}
        self.pending_approvals: Dict[str, Workflow] = {}
        self.workflow_metrics = WorkflowMetrics()
        self._lock = threading.Lock()
    
    def track_workflow(self, workflow: Workflow, user_id: Optional[str] = None) -> None:
        """Begin tracking a new workflow with comprehensive logging"""
        
        with self._lock:
            workflow_id = workflow.id
            
            # Store in active workflows
            self.active_workflows[workflow_id] = workflow
            
            # Update metrics
            self.workflow_metrics.increment_total_workflows()
            if user_id:
                self.workflow_metrics.increment_user_workflows(str(user_id))
            
            # Emit tracking event
            observability.observe(
                event_type=SystemEvents.SERVICE_STARTED,
                level=EventLevel.INFO,
                data={
                    "event": "workflow_tracked",
                    "workflow_id": workflow_id,
                    "user_id": user_id,
                    "status": workflow.status.value,
                    "task_count": len(workflow.tasks),
                    "estimated_duration": workflow.metadata.get("estimated_duration")
                },
                description="Workflow tracked in active workflows"
            )
    
    def update_workflow_status(self, workflow_id: str, workflow: Workflow) -> None:
        """Update workflow status with automatic history management"""
        
        with self._lock:
            if workflow_id in self.active_workflows:
                # Update active workflow
                self.active_workflows[workflow_id] = workflow
                
                # Check if workflow is complete
                if workflow.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]:
                    self._move_to_history(workflow_id, workflow)
                
                # Emit status update event
                observability.observe(
                    event_type=SystemEvents.SERVICE_STARTED,
                    level=EventLevel.INFO,
                    data={
                        "event": "workflow_status_updated",
                        "workflow_id": workflow_id,
                        "status": workflow.status.value,
                        "progress": workflow.progress_percent,
                        "completed_tasks": len(workflow.completed_tasks),
                        "total_tasks": len(workflow.tasks)
                    },
                    description="Workflow status updated"
                )
    
    def _move_to_history(self, workflow_id: str, workflow: Workflow) -> None:
        """Move completed workflow to history"""
        
        # Move to history
        self.workflow_history[workflow_id] = workflow
        del self.active_workflows[workflow_id]
        
        # Update metrics based on final status
        if workflow.status == WorkflowStatus.COMPLETED:
            self.workflow_metrics.increment_completed_workflows()
        elif workflow.status == WorkflowStatus.FAILED:
            self.workflow_metrics.increment_failed_workflows()
        elif workflow.status == WorkflowStatus.CANCELLED:
            self.workflow_metrics.increment_cancelled_workflows()
        
        # Track execution time
        if workflow.started_at and workflow.completed_at:
            execution_time = (workflow.completed_at - workflow.started_at).total_seconds()
            self.workflow_metrics.add_execution_time(execution_time)
```

### Configuration System

```python
@dataclass
class WorkflowConfig:
    """Comprehensive workflow configuration"""
    
    # Core settings
    complexity_method: ComplexityMethod = ComplexityMethod.HEURISTIC
    complexity_threshold: float = 7.0
    routing_strategy: TaskRoutingStrategy = TaskRoutingStrategy.CAPABILITY_BASED
    error_recovery: ErrorRecoveryStrategy = ErrorRecoveryStrategy.RETRY_WITH_BACKOFF
    
    # Performance settings
    max_parallel_tasks: int = 3
    max_concurrent_workflows: int = 10
    
    # Timeout settings
    task_timeout: int = 300  # seconds
    workflow_timeout: int = 3600  # seconds
    enable_adaptive_timeout: bool = True
    
    # Retry settings
    retry: RetryConfig = field(default_factory=lambda: RetryConfig(
        max_attempts=3,
        initial_delay=1.0,
        backoff_factor=2.0
    ))
    
    # Workflow overrides
    overrides: List[WorkflowOverride] = field(default_factory=list)
    routing_rules: List[AgentRoutingRule] = field(default_factory=list)
    
    # Custom functions
    custom_complexity_function: Optional[Callable[[str, Dict], float]] = None
    custom_agent_selector: Optional[Callable[[Task, List[Agent]], Agent]] = None
    
    def get_effective_config(self, request: str) -> 'WorkflowConfig':
        """Get configuration with overrides applied"""
        
        effective_config = copy.deepcopy(self)
        
        # Apply pattern-based overrides
        for override in sorted(self.overrides, key=lambda x: x.priority, reverse=True):
            if self._matches_pattern(request, override.pattern):
                effective_config = self._apply_override(effective_config, override)
                break
        
        return effective_config
    
    def _matches_pattern(self, request: str, pattern: str) -> bool:
        """Check if request matches override pattern"""
        
        # Support regex and simple string matching
        if pattern.startswith("regex:"):
            import re
            return bool(re.search(pattern[6:], request, re.IGNORECASE))
        else:
            return pattern.lower() in request.lower()
```

### Testing Framework

```python
class WorkflowTestSuite:
    """Comprehensive testing framework for workflow system"""
    
    async def test_workflow_end_to_end(self):
        """Test complete workflow execution"""
        
        # Setup test environment
        formation = await self._create_test_formation()
        overlord = await formation.start_overlord()
        
        # Test complex request
        complex_request = "Research AI trends, create a report, and schedule a meeting"
        
        # Execute workflow
        response = await overlord.chat(
            complex_request,
            user_id="test_user",
            session_id="test_session",
            stream=False
        )
        
        # Verify workflow was triggered
        assert hasattr(response, 'metadata')
        assert 'workflow_id' in response.metadata
        
        workflow_id = response.metadata['workflow_id']
        
        # Verify workflow completion
        workflow = await overlord.get_workflow_status(workflow_id)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert len(workflow.completed_tasks) > 0
        
        # Verify response quality
        assert len(response.content) > 100
        assert any(keyword in response.content.lower() for keyword in ['ai', 'trends', 'report'])
        
        await formation.stop_overlord()
    
    async def test_error_recovery(self):
        """Test error recovery mechanisms"""
        
        # Test retry logic
        task = Task(
            id="test_task",
            type="failing_task",
            description="This task will fail initially",
            agent_requirements=["test_agent"]
        )
        
        # Mock failure then success
        with self._mock_task_execution(["failure", "failure", "success"]):
            result = await self.workflow_executor.execute_single_task(task, self._create_test_context())
            
            assert result.status == TaskStatus.COMPLETED
            assert result.attempt_count == 3
    
    async def test_parallel_execution(self):
        """Test parallel task execution"""
        
        # Create independent tasks
        tasks = [
            Task(id=f"task_{i}", type="parallel_task", agent_requirements=["test_agent"])
            for i in range(5)
        ]
        
        start_time = time.time()
        results = await self.workflow_executor._execute_phase_tasks(tasks, self._create_test_context())
        execution_time = time.time() - start_time
        
        # Verify parallel execution (should be much faster than sequential)
        assert execution_time < 2.0  # Tasks should execute in parallel
        assert all(result.status == TaskStatus.COMPLETED for result in results.values())
    
    def _create_test_formation(self) -> Formation:
        """Create test formation with mock agents"""
        # Implementation details...
        pass
```

## Performance Optimization

### Memory Management

```python
class WorkflowMemoryManager:
    """Optimize memory usage for workflow execution"""
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        self._cleanup_interval = 300  # 5 minutes
        
    async def start_cleanup_task(self):
        """Start background cleanup task"""
        
        while True:
            await asyncio.sleep(self._cleanup_interval)
            await self._cleanup_workflow_history()
    
    async def _cleanup_workflow_history(self):
        """Clean up old workflow history entries"""
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        with self.workflow_manager._lock:
            # Find workflows to clean up
            workflows_to_remove = [
                wid for wid, workflow in self.workflow_manager.workflow_history.items()
                if workflow.completed_at and workflow.completed_at < cutoff_time
            ]
            
            # Keep only most recent workflows if over limit
            if len(self.workflow_manager.workflow_history) > self.max_history_size:
                sorted_workflows = sorted(
                    self.workflow_manager.workflow_history.items(),
                    key=lambda x: x[1].completed_at or datetime.min,
                    reverse=True
                )
                
                workflows_to_keep = sorted_workflows[:self.max_history_size]
                workflows_to_remove.extend([
                    wid for wid, _ in sorted_workflows[self.max_history_size:]
                ])
            
            # Remove old workflows
            for workflow_id in workflows_to_remove:
                del self.workflow_manager.workflow_history[workflow_id]
```

### Caching Strategy

```python
class WorkflowCacheManager:
    """Cache frequently used workflow components"""
    
    def __init__(self):
        self.complexity_cache = TTLCache(maxsize=1000, ttl=3600)
        self.decomposition_cache = TTLCache(maxsize=500, ttl=1800)
        self.agent_capability_cache = TTLCache(maxsize=100, ttl=7200)
    
    async def get_cached_complexity(self, request: str) -> Optional[float]:
        """Get cached complexity score"""
        
        request_hash = hashlib.md5(request.encode()).hexdigest()
        return self.complexity_cache.get(request_hash)
    
    async def cache_complexity(self, request: str, complexity: float):
        """Cache complexity score"""
        
        request_hash = hashlib.md5(request.encode()).hexdigest()
        self.complexity_cache[request_hash] = complexity
```

This technical guide provides developers with the detailed implementation knowledge needed to extend, modify, or troubleshoot the MUXI workflow system effectively.