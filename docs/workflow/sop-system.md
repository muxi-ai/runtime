# SOP System Documentation

## Overview

The SOP (Standard Operating Procedures) system in MUXI Runtime provides a powerful mechanism to override default workflow behavior with predefined, structured procedures. SOPs allow you to create repeatable, consistent workflows that are triggered based on specific patterns in user requests.

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [SOP Structure](#sop-structure)
3. [How SOPs Work](#how-sops-work)
4. [Sequential Execution](#sequential-execution)
5. [Creating SOPs](#creating-sops)
6. [SOP Matching](#sop-matching)
7. [Configuration](#configuration)
8. [Examples](#examples)
9. [Advanced Features](#advanced-features)
10. [Troubleshooting](#troubleshooting)

## Core Concepts

### What is an SOP?

An SOP is a predefined workflow template that:
- Overrides default agent routing and task decomposition
- Executes tasks in a specific, predetermined order
- Ensures consistent handling of common request patterns
- Can specify which agents handle which tasks
- Supports resource preloading and MCP tool requirements

### When to Use SOPs

SOPs are ideal for:
- Standardized procedures that should always follow the same steps
- Complex workflows requiring specific task ordering
- Ensuring compliance with organizational processes
- Overriding default system behavior for specific request types
- Creating reproducible workflows with predictable outcomes

## SOP Structure

SOPs are written in Markdown with YAML frontmatter:

```markdown
---
type: sop
name: Your SOP Name
description: Brief description of what this SOP does
mode: template
tags: keyword1, keyword2, keyword3
---

# SOP Title

Description of the SOP's purpose and when it's triggered.

## Steps

1. **Step Name** [agent:optional-agent-id]
   Detailed description of what this step does.
   Additional context or requirements.

2. **Another Step**
   Description of the second step.
   This step depends on outputs from step 1.

3. **Final Step**
   Description of the final step.
   Uses data from previous steps.

## Expected Outcome

What the user should expect when this SOP completes.

## Notes

Additional information about the SOP.
```

### Frontmatter Fields

- **type**: Must be "sop" for the system to recognize it
- **name**: Human-readable name for the SOP
- **description**: Brief description of the SOP's purpose
- **mode**: Execution mode (currently "template" is supported)
- **tags**: Comma-separated keywords for matching user requests

### Step Format

Each step can include:
- **Step name**: Bold text describing the step
- **Agent directive**: `[agent:agent-id]` to specify which agent handles this step
- **Description**: What the step accomplishes
- **Dependencies**: Steps automatically depend on previous steps in sequential SOPs

## How SOPs Work

### 1. Request Processing

When a user makes a request:
1. The system analyzes the request complexity
2. If complexity exceeds threshold, workflow decomposition is triggered
3. The SOP system searches for matching SOPs based on tags and content

### 2. SOP Matching

The system uses semantic matching to find relevant SOPs:
- Compares user request against SOP tags
- Analyzes semantic similarity between request and SOP content
- Returns the most relevant SOP with a relevance score

### 3. Workflow Creation

When an SOP is matched:
1. The SOP template is converted to a Workflow object
2. Tasks are created with sequential dependencies
3. Each task depends on the previous task (for data flow)
4. Agent assignments are preserved from the SOP

### 4. Execution

SOP workflows execute with special handling:
- **Sequential execution** is enforced (parallel execution disabled)
- Tasks run one after another in order
- Each task receives outputs from previous tasks as inputs
- Data flows through the workflow pipeline

## Sequential Execution

### Why Sequential?

SOPs execute sequentially to ensure:
- Proper data flow between dependent tasks
- Predictable execution order
- Each step can build on previous results
- No race conditions or timing issues

### How It Works

```python
# Normal workflows use formation.yaml setting
workflow:
  parallel_execution: true  # Default

# SOP workflows temporarily override
if is_sop_workflow:
    # Force sequential for data dependencies
    config.behavior.enable_parallel_execution = False

# After execution, setting is restored
finally:
    config.behavior.enable_parallel_execution = original_setting
```

### Data Flow

In sequential SOP execution:
1. Task 1 executes and produces outputs
2. Task 2 receives Task 1's outputs as inputs
3. Task 3 receives Task 2's outputs as inputs
4. And so on...

This ensures each step has access to all previous results.

## Creating SOPs

### Step 1: Create SOP File

Create a `.md` file in your formation's `sops/` directory:

```
formation-directory/
├── formation.yaml
├── agents/
└── sops/
    ├── system-report-override.md
    ├── code-review-process.md
    └── incident-response.md
```

### Step 2: Define the SOP

Example SOP for system reporting:

```markdown
---
type: sop
name: System Report Override
description: Generate comprehensive system report instead of creating tickets
mode: template
tags: system, usage, cpu, memory, performance, report
---

# System Report Override

This SOP overrides default ticket creation with a comprehensive system report.

## Steps

1. **Gather system metrics** [agent:it-support]
   Collect CPU, memory, disk, and network statistics.
   Use system monitoring tools to get real-time data.

2. **Analyze performance** 
   Calculate performance scores and identify bottlenecks.
   Compare against baseline metrics.

3. **Generate report** [agent:writer]
   Create a formatted PDF report with:
   - System metrics summary
   - Performance analysis
   - Recommendations
   - Timestamp and host information

## Expected Outcome

A downloadable PDF report with comprehensive system analysis.
```

### Step 3: Enable in Formation

Ensure your formation.yaml has workflow configuration:

```yaml
overlord:
  config:
    workflow:
      auto_decomposition: true
      complexity_threshold: 7.0
      # SOPs will override these settings when matched
```

## SOP Matching

### Tag-Based Matching

SOPs are matched when user requests contain keywords from the SOP's tags:

```python
# User request: "create a linear issue with system usage info"
# Matches SOP with tags: "linear, system, usage, cpu, memory"
```

### Semantic Matching

The system also uses semantic similarity:
- Computes embeddings for user request and SOP content
- Calculates relevance scores
- Selects the highest-scoring SOP above threshold

### Relevance Threshold

Only SOPs with sufficient relevance are triggered:
- Default threshold is configurable
- Prevents false positive matches
- Ensures SOPs only override when truly relevant

## Configuration

### Formation Configuration

```yaml
overlord:
  config:
    workflow:
      # Enable automatic workflow decomposition
      auto_decomposition: true
      
      # Complexity threshold for triggering workflows
      complexity_threshold: 7.0
      
      # Plan approval threshold (higher = requires approval)
      plan_approval_threshold: 10
      
      # Default parallel execution (SOPs override this)
      parallel_execution: true
      
      # Maximum parallel tasks (not used by SOPs)
      max_parallel_tasks: 5
```

### SOP System Configuration

The SOP system initializes automatically when:
- A formation path is provided
- The `sops/` directory exists in the formation
- Auto-decomposition is enabled

## Examples

### Example 1: Code Review SOP

```markdown
---
type: sop
name: Code Review Process
description: Standardized code review workflow
mode: template
tags: code, review, pull request, pr, quality
---

# Code Review Process

## Steps

1. **Analyze code changes** [agent:code-reviewer]
   Review modified files for style and correctness.

2. **Run security scan**
   Check for vulnerabilities and security issues.

3. **Test coverage analysis**
   Verify test coverage meets requirements.

4. **Generate review report** [agent:writer]
   Create comprehensive review with findings and recommendations.
```

### Example 2: Incident Response SOP

```markdown
---
type: sop
name: Incident Response
description: Emergency incident handling procedure
mode: template
tags: incident, emergency, outage, alert, critical
---

# Incident Response

## Steps

1. **Assess severity** [agent:ops-lead]
   Determine incident severity and impact.

2. **Notify stakeholders**
   Send alerts to relevant teams and management.

3. **Gather diagnostics** [agent:it-support]
   Collect logs, metrics, and system state.

4. **Implement fix**
   Apply emergency patches or rollbacks.

5. **Create post-mortem** [agent:writer]
   Document incident timeline and lessons learned.
```

## Advanced Features

### Agent Directives

Specify which agent handles each task:
```markdown
1. **Task name** [agent:specific-agent-id]
```

### Resource Preloading

SOPs can reference external resources:
```markdown
1. **Load configuration**
   Resources: config/settings.yaml
   Apply configuration from file.
```

### MCP Tool Requirements

Specify required MCP tools:
```markdown
1. **System scan** [tools:filesystem,system-info]
   Requires filesystem and system-info MCP servers.
```

### Conditional Steps (Future)

Future enhancement for conditional execution:
```markdown
1. **Check condition**
   If: error_count > 0
   Then: Continue to step 2
   Else: Skip to step 4
```

### Parallel Groups (Future)

Future support for parallel execution within SOPs:
```markdown
2. **Parallel Analysis** [parallel]
   - **CPU analysis**
   - **Memory analysis**  
   - **Disk analysis**
```

## Troubleshooting

### SOP Not Triggering

1. **Check tags**: Ensure tags match keywords in user requests
2. **Verify complexity**: Request must exceed complexity threshold
3. **Check initialization**: Verify SOP system loaded successfully
4. **Review logs**: Look for "SOP matched" events in logs

### Data Not Passing Between Tasks

1. **Verify sequential execution**: Check logs for "sequential execution" mode
2. **Check task dependencies**: Ensure tasks have proper dependency chain
3. **Review task outputs**: Verify tasks are producing expected outputs
4. **Check input collection**: Ensure `_collect_task_inputs` is working

### Wrong SOP Matched

1. **Review tags**: Make tags more specific to avoid false matches
2. **Adjust relevance threshold**: Increase threshold for stricter matching
3. **Check semantic similarity**: Review SOP descriptions for ambiguity
4. **Use unique keywords**: Add distinctive tags for precise matching

### Performance Issues

1. **Check task count**: Too many tasks can slow execution
2. **Review task complexity**: Simplify complex tasks
3. **Monitor timeouts**: Adjust timeouts for long-running tasks
4. **Check agent availability**: Ensure required agents are available

## Best Practices

1. **Keep SOPs focused**: Each SOP should handle one specific procedure
2. **Use descriptive names**: Make SOP purposes clear from the name
3. **Tag thoroughly**: Include all relevant keywords for matching
4. **Document steps clearly**: Each step should have clear objectives
5. **Test thoroughly**: Verify SOPs work as expected before deployment
6. **Version control**: Track SOP changes in git
7. **Review regularly**: Update SOPs as processes evolve
8. **Monitor execution**: Track SOP usage and success rates

## Integration with Workflow System

SOPs integrate seamlessly with the broader workflow system:
- Use the same WorkflowExecutor for execution
- Support all workflow features (monitoring, cancellation, etc.)
- Generate standard workflow events and metrics
- Compatible with resilience and error handling features

See [Workflow Orchestration](orchestration.md) for more details on the underlying workflow system.