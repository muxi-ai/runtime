# MUXI Runtime ID Conventions

This document describes the ID generation conventions used throughout the MUXI Runtime system.

## Overview

All IDs in MUXI Runtime use a consistent format:
- **3-letter prefix** followed by an underscore
- **nanoid** of appropriate length for the use case
- Format: `{prefix}_{nanoid}`

## ID Types and Formats

### 1. Artifact System
- **Artifact ID**: `atf_{nanoid(12)}` - Identifies stored artifacts
- **Execution ID**: `exc_{nanoid(8)}` - Tracks file generation executions

### 2. Scheduler System
- **Job ID**: `job_{nanoid(16)}` - Identifies scheduled jobs

### 3. Agent System
- **Agent ID**: `agt_{nanoid()}` - Unique agent identifier
- **Message ID**: `msg_{nanoid()}` - Inter-agent message identifier

### 4. Clarification System
- **Call ID**: `clr_{nanoid()}` - Tool call identifier
- **Question ID**: `qst_{nanoid()}` - Clarification question identifier

### 5. Document Storage
- **Reference ID**: `ref_{nanoid()}` - Document reference identifier
- **Lineage ID**: `lin_{nanoid()}` - Document lineage tracking

### 6. A2A Communication
- **Message ID**: `msg_{nanoid()}` - A2A message identifier (same as agent)
- **Nonce**: `nnc_{nanoid()}` - Authentication nonce
- **JWT ID**: `jwt_{nanoid()}` - JWT token identifier

### 7. MCP Protocol
- **JSON-RPC ID**: `rpc_{nanoid()}` - RPC request identifier

### 8. Workflow System
- **Workflow ID**: `wrk_{nanoid()}` - Workflow identifier
- **Task ID**: `task_{nanoid()}` - Task within workflow

### 9. UI Components
- **Button ID**: `btn_{nanoid()}` - Interactive button identifier
- **Form ID**: `frm_{nanoid()}` - Form element identifier
- **Chart ID**: `chr_{nanoid()}` - Chart visualization identifier
- **Table ID**: `tbl_{nanoid()}` - Table component identifier

### 10. Resource Management
- **Allocation ID**: `alc_{nanoid()}` - Resource allocation identifier
- **Plan ID**: `pln_{nanoid()}` - Execution plan identifier

## Implementation

All ID generation uses the centralized `generate_nanoid()` function from `muxi.runtime.utils.id_generator`.

### Basic Usage

```python
from muxi.runtime.utils.id_generator import generate_nanoid

# Standard ID (21 characters)
agent_id = f"agt_{generate_nanoid()}"

# Custom length ID
artifact_id = f"art_{generate_nanoid(size=12)}"
```

### Size Guidelines

- **Default size (21)**: Used for most IDs where uniqueness is critical
- **Size 16**: Used for scheduled jobs that need medium uniqueness
- **Size 12**: Used for artifacts where the combination with timestamp provides uniqueness
- **Size 8**: Used for short-lived execution tracking

## Migration Notes

The system supports backward compatibility for some legacy ID formats:
- Workflow IDs accept: `wrk_`, `wf_`, or `workflow_` prefixes
- Other systems have been fully migrated to the 3-letter format

## Benefits

1. **Consistency**: All IDs follow the same pattern
2. **Readability**: 3-letter prefixes make IDs instantly recognizable
3. **Debugging**: Easy to identify which system generated an ID
4. **URL-safe**: nanoid uses URL-safe characters by default
5. **Performance**: nanoid is faster than UUID generation
6. **Size**: Shorter than UUIDs while maintaining uniqueness
