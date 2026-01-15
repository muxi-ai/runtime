# MUXI Agent Protocol (MAP) Specification

**Version:** 0.1.0 (Draft)  
**Status:** Proposal  
**Target:** Q1 2026  
**Authors:** MUXI Team  

---

## Abstract

The MUXI Agent Protocol (MAP) defines a standardized communication protocol between MUXI formations (server-side) and autonomous agents running on end-user machines (client-side). Similar to how MCP standardized tool integration, MAP standardizes remote agent coordination.

The protocol enables server-side AI systems to dispatch tasks to client-side agents that have their own intelligence (LLM) and can execute complex, multi-step operations on the user's machine autonomously.

---

## Motivation

### The Enterprise IT Problem

**Today's IT Support Model:**

```
Employee: "My Outlook won't sync"
     ↓
Ticket created in ServiceNow
     ↓
Sits in queue for hours/days
     ↓
IT technician picks up ticket
     ↓
Schedules remote session with employee
     ↓
30-minute call: "Click here... now there... try restarting..."
     ↓
Issue resolved (maybe)
     ↓
Total time: 2-5 days
```

**With MAP-Enabled Agents:**

```
Employee (via Slack): "My Outlook won't sync"
     ↓
MUXI formation receives message
     ↓
Looks up employee's registered computer agent
     ↓
Dispatches diagnostic task to agent
     ↓
Agent autonomously: checks settings, clears cache, verifies credentials
     ↓
Auto-resolves OR escalates with full diagnostic report
     ↓
Total time: 2 minutes
```

### The "Left It at Work" Problem

**Today:**
> "I need that proposal document but I left it on my work computer. I'll have to wait until Monday."

**With MAP:**
> Employee (via WhatsApp at 10 PM): "Send me the Johnson proposal from my desktop"
> 
> MUXI: "Found 'Johnson_Proposal_v3.docx' on your work machine. Sending now."
> 
> *File arrives in WhatsApp*

### Why a Protocol?

- **Interoperability** - Any compliant agent works with any MUXI formation
- **Vendor neutrality** - Not locked to one computer-use implementation
- **Security standardization** - Common auth, audit, and permission patterns
- **Ecosystem growth** - Third parties can build MAP-compliant agents

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         End User's Machine                           │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    MAP-Compliant Agent                          │ │
│  │                    (e.g., OpenWork-based)                       │ │
│  │                                                                 │ │
│  │   ┌───────────┐    ┌───────────┐    ┌───────────────────────┐  │ │
│  │   │  Local    │───▶│  Action   │───▶│  OS Integration       │  │ │
│  │   │  LLM      │    │  Planner  │    │  (screen/mouse/kb/fs) │  │ │
│  │   └───────────┘    └───────────┘    └───────────────────────┘  │ │
│  │         ▲                                                       │ │
│  │         │                                                       │ │
│  │   ┌─────┴─────┐                                                 │ │
│  │   │    MAP    │◀════════════════════════════════════════════════╬══╗
│  │   │  Handler  │════════════════════════════════════════════════▶╬══╬═╗
│  │   └───────────┘         (receive tasks)         (callbacks)     │ │ ║ ║
│  └─────────────────────────────────────────────────────────────────┘ │ ║ ║
└──────────────────────────────────────────────────────────────────────╬─╬─╬─┘
                                                                       ║ ║ ║
                         ══════ MAP Protocol ══════                    ║ ║ ║
                                                                       ║ ║ ║
┌──────────────────────────────────────────────────────────────────────╬─╬─╬─┐
│                           MUXI Formation                             ║ ║ ║ │
│                                                                      ║ ║ ║ │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────────┐    ║ ║ ║ │
│  │   User       │────▶│   Overlord    │────▶│  Agent Registry  │    ║ ║ ║ │
│  │   Interface  │     │               │     │                  │    ║ ║ ║ │
│  │  (Slack/WA)  │     └───────┬───────┘     │  user_id: abc    │    ║ ║ ║ │
│  └──────────────┘             │             │  endpoint: ...   │    ║ ║ ║ │
│                               │             │  api_key: ...    │    ║ ║ ║ │
│                               ▼             │  capabilities:[] │    ║ ║ ║ │
│                    ┌───────────────────┐    └────────┬─────────┘    ║ ║ ║ │
│                    │   MAP Gateway     │◀────────────┘              ║ ║ ║ │
│                    │                   │                            ║ ║ ║ │
│                    │  • Dispatch tasks │══════════ send task ══════▶╝ ║ ║ │
│                    │  • Handle callbacks│◀═════════ progress ═════════╝ ║ │
│                    │  • Route approvals │◀═════════ approval ═══════════╝ │
│                    └───────────────────┘                                  │
└───────────────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Intelligence on the Edge** - The agent has its own LLM and decision-making capability. The protocol only handles communication, not computation.

2. **Formation as Coordinator** - The MUXI formation knows which users have agents, their capabilities, and how to reach them. It coordinates but doesn't control.

3. **Callback-Based Progress** - Agents report progress asynchronously via callbacks, allowing long-running tasks without blocking.

4. **Human-in-the-Loop** - Sensitive actions require user approval, routed through the same interface (Slack/WhatsApp) the user initiated from.

---

## Protocol Specification

### Transport

- **Primary:** HTTPS/1.1 or HTTPS/2
- **Content-Type:** `application/json`
- **Character Encoding:** UTF-8

### Authentication

**Formation → Agent:**
```
Authorization: Bearer map_sk_<agent_api_key>
```

**Agent → Formation (callbacks):**
```
Authorization: Bearer <callback_token>
```

Callback tokens are task-specific and short-lived.

### Endpoints

#### Agent Endpoints (implemented by client agent)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/map/v1/tasks` | Create a new task |
| DELETE | `/map/v1/tasks/{task_id}` | Cancel a running task |
| GET | `/map/v1/health` | Health check |
| GET | `/map/v1/capabilities` | List agent capabilities |

#### Formation Endpoints (callback receiver)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/map/v1/callback` | Receive task updates |

---

## Message Types

### Task Create

**Request:** `POST /map/v1/tasks`

```json
{
  "jsonmap": "1.0",
  "id": "task_abc123def456",
  "callback_url": "https://formation.example.com/map/v1/callback",
  "callback_token": "cb_xyz789...",
  
  "intent": "Fix Outlook sync issue",
  "context": {
    "user_message": "My email hasn't synced since yesterday morning",
    "user_id": "employee_12345",
    "known_context": [
      "User is on Windows 11",
      "Recent Office update deployed last week",
      "No VPN issues reported"
    ]
  },
  
  "constraints": {
    "timeout_seconds": 300,
    "max_actions": 50,
    "require_approval_for": ["install_software", "modify_registry", "delete_files"],
    "allowed_applications": ["outlook", "settings", "control_panel", "browser"],
    "blocked_applications": ["cmd", "powershell", "regedit"]
  },
  
  "preferences": {
    "screenshot_frequency": "on_action",
    "verbosity": "detailed"
  }
}
```

**Response:** `202 Accepted`

```json
{
  "task_id": "task_abc123def456",
  "status": "accepted",
  "estimated_duration_seconds": 120
}
```

### Task Progress

**Callback:** `POST {callback_url}`

```json
{
  "jsonmap": "1.0",
  "task_id": "task_abc123def456",
  "type": "task.progress",
  "timestamp": "2026-03-15T10:30:45Z",
  
  "progress": {
    "step": 3,
    "total_steps_estimate": 8,
    "percentage": 37,
    "current_action": "Checking Outlook account settings",
    "status": "executing"
  },
  
  "evidence": {
    "screenshot_base64": "iVBORw0KGgo...",
    "action_description": "Opened Outlook > File > Account Settings"
  }
}
```

### Task Approval Request

When the agent needs human confirmation:

```json
{
  "jsonmap": "1.0",
  "task_id": "task_abc123def456",
  "type": "task.approval_required",
  "timestamp": "2026-03-15T10:31:20Z",
  
  "approval": {
    "action": "Clear Outlook local cache",
    "reason": "This will delete locally cached emails and require re-download",
    "impact": "medium",
    "reversible": false,
    "screenshot_base64": "iVBORw0KGgo...",
    "options": [
      {"id": "approve", "label": "Yes, clear cache"},
      {"id": "deny", "label": "No, skip this"},
      {"id": "abort", "label": "Stop and escalate to IT"}
    ],
    "timeout_seconds": 300,
    "default_on_timeout": "deny"
  }
}
```

The formation routes this to the user via their communication channel (Slack/WhatsApp).

### Approval Response

**Request:** `POST /map/v1/tasks/{task_id}/approval`

```json
{
  "approval_id": "appr_xyz789",
  "decision": "approve",
  "decided_by": "user",
  "timestamp": "2026-03-15T10:32:00Z"
}
```

### Task Completed

```json
{
  "jsonmap": "1.0",
  "task_id": "task_abc123def456",
  "type": "task.completed",
  "timestamp": "2026-03-15T10:33:15Z",
  
  "result": {
    "success": true,
    "summary": "Outlook sync issue resolved. Cleared corrupted OST file and re-synced mailbox.",
    "details": "The local cache file was corrupted, likely from the recent update. After clearing and re-syncing, 847 emails were downloaded successfully.",
    "actions_taken": 12,
    "duration_seconds": 150
  },
  
  "evidence": {
    "action_log": [
      {"step": 1, "action": "Opened Outlook", "success": true, "duration_ms": 2300},
      {"step": 2, "action": "Navigated to Account Settings", "success": true, "duration_ms": 800},
      {"step": 3, "action": "Identified sync error in status", "success": true, "duration_ms": 500},
      {"step": 4, "action": "Closed Outlook", "success": true, "duration_ms": 1200},
      {"step": 5, "action": "Located OST file in AppData", "success": true, "duration_ms": 3400},
      {"step": 6, "action": "Requested approval to delete cache", "success": true, "duration_ms": 45000},
      {"step": 7, "action": "Deleted corrupted OST file", "success": true, "duration_ms": 200},
      {"step": 8, "action": "Reopened Outlook", "success": true, "duration_ms": 4500},
      {"step": 9, "action": "Triggered manual sync", "success": true, "duration_ms": 800},
      {"step": 10, "action": "Waited for sync completion", "success": true, "duration_ms": 89000},
      {"step": 11, "action": "Verified email count restored", "success": true, "duration_ms": 1200},
      {"step": 12, "action": "Confirmed sync status healthy", "success": true, "duration_ms": 600}
    ],
    "screenshots": {
      "before": "iVBORw0KGgo...",
      "after": "iVBORw0KGgo..."
    }
  },
  
  "recommendations": [
    "Consider scheduling Office updates during off-hours to reduce sync interruptions"
  ]
}
```

### Task Failed

```json
{
  "jsonmap": "1.0",
  "task_id": "task_abc123def456",
  "type": "task.failed",
  "timestamp": "2026-03-15T10:35:00Z",
  
  "error": {
    "code": "UNABLE_TO_RESOLVE",
    "message": "Could not fix the sync issue automatically",
    "reason": "The Exchange server is returning authentication errors that require admin intervention",
    "actions_attempted": 8,
    "duration_seconds": 180
  },
  
  "evidence": {
    "action_log": [...],
    "screenshots": {...},
    "diagnostic_data": {
      "error_codes": ["0x800CCC0E", "0x80040154"],
      "server_response": "Authentication failed - account locked"
    }
  },
  
  "recommendations": [
    "User's Exchange account may be locked - IT admin should check Active Directory",
    "Possible password expiration - user may need to update credentials"
  ],
  
  "escalation": {
    "suggested_team": "Exchange Administrators",
    "priority": "medium",
    "full_diagnostic_attached": true
  }
}
```

### Task Cancelled

**Request:** `DELETE /map/v1/tasks/{task_id}`

**Response:** `200 OK`

```json
{
  "task_id": "task_abc123def456",
  "status": "cancelled",
  "cleanup_performed": true
}
```

---

## Agent Registration

Agents must be registered with the formation before receiving tasks. This is typically done during agent installation on the user's machine.

### Registration Request

```json
{
  "user_id": "employee_12345",
  "agent_version": "1.0.0",
  "endpoint": "https://workstation-abc.corp.example.com:8443/map/v1",
  "capabilities": [
    "browser_control",
    "application_control", 
    "file_system_read",
    "file_system_write",
    "clipboard_access",
    "screenshot_capture"
  ],
  "os": {
    "platform": "windows",
    "version": "11",
    "arch": "x64"
  },
  "installed_applications": [
    "Microsoft Outlook",
    "Microsoft Word",
    "Google Chrome",
    "Slack"
  ]
}
```

### Registration Response

```json
{
  "agent_id": "agent_xyz789",
  "api_key": "map_sk_live_...",
  "registered_at": "2026-03-01T09:00:00Z",
  "permissions": {
    "granted": ["browser_control", "application_control", "file_system_read", "screenshot_capture"],
    "denied": ["file_system_write"],
    "require_approval": ["clipboard_access"]
  }
}
```

### Endpoint Discovery

For agents behind NAT/firewalls, several options exist:

1. **Static endpoint** - Agent has public IP or corporate VPN
2. **Tunnel service** - Agent uses ngrok, Cloudflare Tunnel, or similar
3. **Polling mode** - Agent polls formation for tasks (fallback)

```json
{
  "endpoint_type": "tunnel",
  "tunnel_provider": "cloudflare",
  "endpoint": "https://agent-abc123.cfargotunnel.com/map/v1"
}
```

---

## Capabilities

Standard capability identifiers:

| Capability | Description |
|------------|-------------|
| `browser_control` | Navigate, click, type in web browsers |
| `application_control` | Open, close, interact with desktop applications |
| `file_system_read` | Read files and directories |
| `file_system_write` | Create, modify, delete files |
| `file_transfer` | Send files to formation/user |
| `clipboard_access` | Read/write system clipboard |
| `screenshot_capture` | Take screenshots |
| `screen_recording` | Record screen video |
| `terminal_access` | Execute terminal commands |
| `system_settings` | Modify OS settings |
| `software_install` | Install/uninstall software |

---

## Security Considerations

### Authentication & Authorization

- Agent API keys should be rotated regularly
- Callback tokens are single-use and task-scoped
- All communication must use TLS 1.3+

### Permission Scoping

Enterprises define permission policies:

```yaml
# Example enterprise policy
permissions:
  default:
    allow:
      - browser_control
      - application_control
      - file_system_read
      - screenshot_capture
    deny:
      - terminal_access
      - software_install
      - system_settings
    require_approval:
      - file_system_write
      - file_transfer
      
  it_support_tasks:
    allow:
      - terminal_access
      - system_settings
    require_approval:
      - software_install
```

### Audit Trail

All task executions must be logged with:
- Full action log
- Screenshots at key steps
- User approvals with timestamps
- Task initiator identity

### User Visibility

The agent SHOULD provide visual indication when active:
- System tray icon showing status
- Optional: on-screen overlay during execution
- Notification when task starts/completes

---

## Example Use Cases

### 1. IT Support Automation

**User (Slack):** "Outlook keeps crashing when I open attachments"

**Formation:**
1. Looks up user's registered agent
2. Dispatches diagnostic task
3. Agent checks Outlook logs, repairs Office installation
4. Reports resolution or escalates with diagnostics

### 2. Remote File Retrieval

**User (WhatsApp, 10 PM from home):** "Send me the Q4 report from my desktop"

**Formation:**
1. Dispatches file search task to user's work machine
2. Agent locates file: `C:\Users\john\Documents\Q4_Report_Final.xlsx`
3. Agent sends file to formation via callback
4. Formation delivers file to user via WhatsApp

### 3. Software Deployment

**IT Admin (via admin dashboard):** "Deploy new VPN client to all sales team machines"

**Formation:**
1. Queries agent registry for sales team members with registered agents
2. Dispatches installation task to each (with approval required)
3. Users receive Slack message: "IT needs to install updated VPN client. Approve?"
4. On approval, agent downloads and installs silently
5. Reports success/failure to IT dashboard

### 4. Compliance Verification

**Scheduled task (weekly):** "Verify all machines have updated antivirus"

**Formation:**
1. Dispatches verification task to all registered agents
2. Each agent checks antivirus status, version, last scan date
3. Agents report back
4. Formation generates compliance report, flags non-compliant machines

---

## Reference Implementation

A reference implementation based on [OpenWork](https://github.com/accomplish-ai/openwork) (MIT licensed) is planned.

The reference implementation will include:
- MAP protocol handler
- Integration with OpenWork's computer use capabilities
- Registration flow with MUXI formations
- Cross-platform support (Windows, macOS, Linux)

---

## Future Considerations

### Multi-Agent Coordination

Future versions may support tasks spanning multiple user machines:
- "Find who has the latest version of the marketing deck"
- "Sync this folder across all team members' machines"

### Agent-to-Agent Communication

Agents may need to coordinate directly for some workflows:
- Peer file transfer (without going through formation)
- Collaborative tasks

### Offline Task Queuing

For laptops that go offline:
- Formation queues tasks
- Agent polls for tasks when online
- Graceful handling of stale tasks

---

## Appendix A: Error Codes

| Code | Description |
|------|-------------|
| `TASK_ACCEPTED` | Task accepted and queued |
| `TASK_STARTED` | Task execution began |
| `TASK_COMPLETED` | Task finished successfully |
| `TASK_FAILED` | Task failed (see error details) |
| `TASK_CANCELLED` | Task was cancelled |
| `TASK_TIMEOUT` | Task exceeded timeout |
| `APPROVAL_TIMEOUT` | User didn't respond to approval in time |
| `APPROVAL_DENIED` | User denied the approval request |
| `CAPABILITY_UNAVAILABLE` | Agent lacks required capability |
| `PERMISSION_DENIED` | Enterprise policy blocks action |
| `AGENT_OFFLINE` | Agent is not reachable |
| `AGENT_BUSY` | Agent is executing another task |

---

## Appendix B: JSON Schema

Full JSON schemas for all message types are available at:
`https://schemas.muxi.org/map/v1/`

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-01 | Initial draft |

---

## References

- [MCP Protocol](https://modelcontextprotocol.io/) - Inspiration for protocol design
- [OpenWork](https://github.com/accomplish-ai/openwork) - Reference computer use implementation
- [MUXI Runtime](https://github.com/muxi-ai/runtime) - Formation execution environment
