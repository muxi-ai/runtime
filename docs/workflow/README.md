# MUXI Workflow System Documentation

The MUXI Runtime Workflow System provides intelligent task decomposition and multi-agent coordination for complex requests. This directory contains comprehensive documentation for understanding and working with the workflow system.

## 📚 Documentation Structure

### Core Documentation

1. **[Workflow Orchestration](orchestration.md)**
   - Overview of the workflow system architecture
   - Core components and their responsibilities
   - Request flow and complexity analysis
   - Configuration reference

2. **[Workflow Resilience Integration](resilience_integration.md)**
   - Resilience layer architecture
   - Error classification and recovery strategies
   - User-friendly error messages
   - Configuration for retry and fallback mechanisms

3. **[Workflow Technical Guide](technical_guide.md)**
   - Deep dive into implementation details
   - Task decomposition algorithm
   - Workflow execution engine
   - Advanced patterns and optimizations

### Reference Guides

4. **[Workflow Quick Reference](quick_reference.md)**
   - Common workflow patterns
   - Configuration examples
   - Troubleshooting tips
   - Best practices

5. **[SOP System](sop-system.md)** 🆕
   - Standard Operating Procedures with intelligent decomposition
   - Template (strict) vs Guide (flexible) execution modes
   - 40-80% performance improvement over mechanical execution
   - Simplified architecture with zero parsing overhead

6. **[Workflow Status Endpoints](status_endpoints.md)**
   - API endpoints for workflow monitoring
   - Status tracking and management
   - Integration with external systems

7. **[Deferred Async Execution](deferred_async_execution.md)**
   - Approval-aware async decision logic
   - Post-approval async re-evaluation
   - Webhook notifications for background execution
   - Migration guide and troubleshooting

## 🚀 Getting Started

If you're new to the MUXI Workflow System, we recommend reading the documentation in this order:

1. Start with [Workflow Orchestration](orchestration.md) to understand the overall system
2. Review [Workflow Quick Reference](quick_reference.md) for practical examples
3. Learn about [SOP System](sop-system.md) for workflow overrides 🆕
4. Explore [Workflow Resilience Integration](resilience_integration.md) to understand error handling
5. Dive into [Workflow Technical Guide](technical_guide.md) for implementation details

## 🔧 Key Features

- **Intelligent Task Decomposition**: Automatically breaks complex requests into manageable tasks
- **Multi-Agent Coordination**: Routes tasks to specialized agents based on capabilities
- **Parallel Execution**: Executes independent tasks concurrently for optimal performance
- **SOP System**: Intelligent execution of predefined procedures via decomposer 🆕
- **Approval Workflows**: Requires user confirmation for high-stakes operations
- **Resilience Layer**: Automatic retry, graceful degradation, and user-friendly error messages
- **Configurable Complexity Analysis**: Multiple methods for determining request complexity

## 📋 Configuration Example

```yaml
overlord:
  config:
    # Enable workflow features
    auto_decomposition: true
    plan_approval_threshold: 7
    
    workflow:
      complexity_threshold: 6.0
      routing_strategy: "capability_based"
      parallel_execution: true
      
      # Resilience configuration
      error_recovery: "retry_with_backoff"
      retry:
        max_attempts: 5
        initial_delay: 2.0
        backoff_factor: 2.0
```

## 🛠️ Development

For contributors working on the workflow system:

- Source code: `src/muxi/formation/workflow/`
- Tests: `tests/day_7/`
- Examples: See the demo scripts in the test directory

## 📊 Monitoring

The workflow system provides comprehensive observability:

- Event streaming for all workflow operations
- Metrics collection for performance analysis
- Status endpoints for real-time monitoring
- Integration with external monitoring systems

For more details, see [Workflow Status Endpoints](status_endpoints.md).

## 🤝 Contributing

When contributing to the workflow system:

1. Follow the patterns established in existing code
2. Add tests for new functionality
3. Update relevant documentation
4. Consider resilience implications for new features

## 📞 Support

For questions or issues related to the workflow system:

1. Check the [Quick Reference](quick_reference.md) for common patterns
2. Review error messages - they're designed to be helpful!
3. Consult the [Technical Guide](technical_guide.md) for deep debugging
4. Open an issue in the repository for bugs or feature requests