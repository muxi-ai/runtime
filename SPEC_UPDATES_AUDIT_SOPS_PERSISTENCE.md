# OpenAPI Spec Updates: Audit, SOPs, and Persistence

**Date:** 2025-10-23  
**Purpose:** Add audit logging, SOP endpoints, and document persistence requirements

---

## Changes Required

### 1. Add New Tags

```yaml
tags:
  - name: Audit
    description: Audit log for formation changes
  - name: SOPs
    description: Standard Operating Procedures (read-only)
```

### 2. Add Audit Endpoints

**After `/a2a` endpoints, before `/chat`:**

```yaml
  # Audit Log
  /audit:
    get:
      tags: [Audit]
      summary: Get audit log
      description: |
        Retrieve formation change audit trail. Returns most recent entries first.
        
        The audit log tracks all formation-modifying operations:
        - Agent create/update/delete
        - Secret create/delete
        - MCP server create/update/delete
        - Scheduler job create/delete and config changes
        - Logging destination create/update/delete and config changes
        - Async config changes (webhook URL, etc.)
        - Memory delete operations (admin)
        
        Log location: `~/.muxi/formations/{formation_id}/audit.log`
        Format: JSONL (one JSON object per line) with human-readable message
      operationId: getAuditLog
      security:
        - AdminKey: []
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            minimum: 1
            maximum: 1000
          description: Maximum number of entries to return (most recent first)
        - name: action
          in: query
          schema:
            type: string
          description: Filter by action type (e.g., agent.created, secret.deleted)
        - name: resource_type
          in: query
          schema:
            type: string
            enum: [agent, secret, mcp_server, scheduler_job, logging_destination, async, memory]
          description: Filter by resource type
        - name: since
          in: query
          schema:
            type: string
            format: date-time
          description: Return entries since this ISO 8601 timestamp
      responses:
        '200':
          description: Audit log entries
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                audit_entries:
                  value:
                    object: "audit_log"
                    timestamp: 1706616000000
                    type: "audit.retrieved"
                    request:
                      id: "req_audit123"
                      idempotency_key: null
                    success: true
                    error: null
                    data:
                      entries:
                        - timestamp: "2025-10-23T14:23:45.123Z"
                          request_id: "req_abc123"
                          action: "agent.created"
                          resource_type: "agent"
                          resource_id: "weather-bot"
                          user: "admin"
                          ip: "192.168.1.100"
                          result: "success"
                          status_code: 201
                          message: "Agent 'weather-bot' created by admin"
                        - timestamp: "2025-10-23T14:24:10.456Z"
                          request_id: "req_xyz789"
                          action: "agent.deleted"
                          resource_type: "agent"
                          resource_id: "old-bot"
                          user: "admin"
                          ip: "192.168.1.100"
                          result: "success"
                          status_code: 200
                          message: "Agent 'old-bot' deleted by admin"
                        - timestamp: "2025-10-23T14:25:33.789Z"
                          request_id: "req_def456"
                          action: "secret.created"
                          resource_type: "secret"
                          resource_id: "OPENAI_KEY"
                          user: "admin"
                          ip: "192.168.1.100"
                          result: "success"
                          status_code: 201
                          message: "Secret 'OPENAI_KEY' created by admin"
                      count: 3
                      total_entries: 47

    delete:
      tags: [Audit]
      summary: Clear audit log
      description: |
        Clear the audit log file. Use with caution!
        
        **This action itself is audited** - creates a final entry documenting
        who cleared the log and when, then resets the log to contain only that entry.
        
        Requires explicit confirmation parameter to prevent accidental deletion.
      operationId: clearAuditLog
      security:
        - AdminKey: []
      parameters:
        - name: confirm
          in: query
          required: true
          schema:
            type: string
            enum: ["clear-audit-log"]
          description: Required confirmation string to prevent accidental deletion
      responses:
        '200':
          description: Audit log cleared
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                cleared:
                  value:
                    object: "audit_log"
                    timestamp: 1706616000000
                    type: "audit.cleared"
                    request:
                      id: "req_clear123"
                      idempotency_key: null
                    success: true
                    error: null
                    data:
                      message: "Audit log cleared successfully"
                      previous_entries_count: 47
                      cleared_by: "admin"
        '400':
          description: Missing or invalid confirmation
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                missing_confirmation:
                  value:
                    object: "error"
                    timestamp: 1706616000000
                    type: "error.validation"
                    request:
                      id: "req_clear456"
                      idempotency_key: null
                    success: false
                    error:
                      code: "INVALID_REQUEST"
                      message: "Confirmation required: add ?confirm=clear-audit-log"
                      data: null
                    data: {}
```

### 3. Add SOP Endpoints

**After `/audit`, before `/chat`:**

```yaml
  # Standard Operating Procedures (SOPs)
  /sops:
    get:
      tags: [SOPs]
      summary: List available SOPs
      description: |
        List all Standard Operating Procedures defined in the formation.
        
        SOPs are workflow templates stored in `formation_path/sops/` directory.
        They define multi-step procedures with agent routing for complex operations.
        
        **Read-only**: SOPs are formation-defined and cannot be modified via API.
        They must be updated in the formation YAML files and redeployed.
      operationId: listSOPs
      security:
        - ClientKey: []
      responses:
        '200':
          description: List of available SOPs
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                sops_available:
                  value:
                    object: "sop_list"
                    timestamp: 1706616000000
                    type: "sops.list"
                    request:
                      id: "req_sop123"
                      idempotency_key: null
                    success: true
                    error: null
                    data:
                      sops:
                        - name: "customer-onboarding"
                          title: "Customer Onboarding Procedure"
                          type: "template"
                          steps: 5
                          agents_used: ["identity-verifier", "account-manager", "communication"]
                        - name: "incident-response"
                          title: "Security Incident Response"
                          type: "guide"
                          steps: 8
                          agents_used: ["security-analyst", "incident-coordinator"]
                      count: 2

  /sops/{sop_name}:
    get:
      tags: [SOPs]
      summary: Get SOP details
      description: |
        Get detailed information about a specific Standard Operating Procedure.
        
        Returns the SOP metadata and content, including:
        - Full markdown content
        - Frontmatter metadata
        - Referenced files (if any)
        - Execution mode (template vs guide)
        
        **Read-only**: SOPs cannot be modified via API.
      operationId: getSOPDetails
      security:
        - ClientKey: []
      parameters:
        - name: sop_name
          in: path
          required: true
          description: Name of the SOP (without .md extension)
          schema:
            type: string
            example: "customer-onboarding"
      responses:
        '200':
          description: SOP details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                sop_details:
                  value:
                    object: "sop"
                    timestamp: 1706616000000
                    type: "sop.retrieved"
                    request:
                      id: "req_sop456"
                      idempotency_key: null
                    success: true
                    error: null
                    data:
                      name: "customer-onboarding"
                      title: "Customer Onboarding Procedure"
                      type: "template"
                      content: |
                        ---
                        type: sop
                        title: Customer Onboarding Procedure
                        ---

                        1. Verify customer identity
                           - Agent: identity-verifier
                           - Check documents

                        2. Set up account
                           - Agent: account-manager
                           - Create profiles
                      metadata:
                        type: "sop"
                        title: "Customer Onboarding Procedure"
                      references:
                        - "file:templates/welcome.md"
                      agents_used:
                        - "identity-verifier"
                        - "account-manager"
                      steps: 5
        '404':
          description: SOP not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                not_found:
                  value:
                    object: "error"
                    timestamp: 1706616000000
                    type: "error.not_found"
                    request:
                      id: "req_sop789"
                      idempotency_key: null
                    success: false
                    error:
                      code: "RESOURCE_NOT_FOUND"
                      message: "SOP 'unknown-sop' not found"
                      data: null
                    data: {}
```

### 4. Update Scheduler Job Endpoints

**Update POST /scheduler/jobs response:**

```yaml
    post:
      # ... existing content ...
      responses:
        '201':
          # ... existing 201 response ...
        '422':
          description: Persistent memory not configured
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse'
              examples:
                no_persistent_memory:
                  value:
                    object: "error"
                    timestamp: 1706616000000
                    type: "error.validation"
                    request:
                      id: "req_job456"
                      idempotency_key: null
                    success: false
                    error:
                      code: "UNPROCESSABLE_ENTITY"
                      message: "Scheduler jobs require persistent memory (non-SQLite database)"
                      data:
                        reason: "Formation is using SQLite or no persistent memory"
                        required: "PostgreSQL or MySQL for scheduler job persistence"
                        current_memory_type: "sqlite"
                    data: {}
```

### 5. Add New Event Types to api.py

```python
# Audit events
AUDIT_RETRIEVED = "audit.retrieved"
AUDIT_CLEARED = "audit.cleared"

# SOP events
SOPS_LIST = "sops.list"
SOP_RETRIEVED = "sop.retrieved"
```

### 6. Add New Object Types to api.py

```python
# Audit objects
AUDIT_LOG = "audit_log"

# SOP objects
SOP = "sop"
SOP_LIST = "sop_list"
```

### 7. Update Endpoint Descriptions for Persistence

**Add to each modification endpoint:**

```yaml
# Agent endpoints
POST /agents:
  description: |
    ...existing description...
    
    **Persistence**: Agent is saved to `agents/{agent_id}.yaml` and survives restarts.

PATCH /agents/{agent_id}:
  description: |
    ...existing description...
    
    **Persistence**: Changes are written to `agents/{agent_id}.yaml` atomically.

DELETE /agents/{agent_id}:
  description: |
    ...existing description...
    
    **Note**: Only agents created via API (source="api") can be deleted.
    Formation-defined agents (source="formation") cannot be removed.
    
    **Persistence**: Agent file `agents/{agent_id}.yaml` is deleted.

# Async endpoint
PATCH /async:
  description: |
    ...existing description...
    
    **Persistence**: Changes are written to `formation.yaml` atomically and survive restarts.

# Logging endpoints
POST /logging/destinations:
  description: |
    ...existing description...
    
    **Persistence**: Destination is added to `formation.yaml` and survives restarts.

# Scheduler endpoints  
POST /scheduler/jobs:
  description: |
    Create a new scheduled job (one-time or recurring).
    
    **Persistence**: Jobs are stored in the database and require persistent memory
    (PostgreSQL or MySQL). Returns 422 error if formation uses SQLite or no persistence.
    
    **Database Storage**: Jobs survive formation restarts and are loaded on startup.
```

---

## Summary of Changes

### New Endpoints (4)
1. `GET /audit` - Retrieve audit log
2. `DELETE /audit` - Clear audit log  
3. `GET /sops` - List SOPs
4. `GET /sops/{sop_name}` - Get SOP details

### Updated Endpoints (15+)
- POST /scheduler/jobs - Add 422 response for no persistent memory
- POST /agents - Document persistence behavior
- PATCH /agents/{id} - Document persistence behavior
- DELETE /agents/{id} - Document source="api" restriction
- POST /mcp/servers - Document persistence behavior (when implemented)
- PATCH /async - Document persistence behavior
- POST /logging/destinations - Document persistence behavior
- All other modification endpoints - Add persistence notes

### New Datatypes (6)
- 2 new event types (audit, sops)
- 2 new object types (audit, sops)
- Update existing schemas with persistence notes

---

## Implementation Checklist

**Spec Changes:**
- [ ] Add Audit and SOPs tags
- [ ] Add GET /audit endpoint
- [ ] Add DELETE /audit endpoint
- [ ] Add GET /sops endpoint
- [ ] Add GET /sops/{sop_name} endpoint
- [ ] Update POST /scheduler/jobs with 422 response
- [ ] Add persistence notes to all modification endpoints
- [ ] Add source="api" restriction notes to delete endpoints

**Code Changes (Separate Task):**
- [ ] Implement AuditLogger class
- [ ] Add audit middleware
- [ ] Implement audit endpoints
- [ ] Implement SOP endpoints
- [ ] Add persistent memory check to scheduler
- [ ] Add atomic formation.yaml updates
- [ ] Add MCP server file persistence
- [ ] Update all api.py datatypes

