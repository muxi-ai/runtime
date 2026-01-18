# MUXI Desktop Agent (MDA)

**Product Requirements Document**
Architecture • UX • Implementation

------

## Executive Summary

MDA (MUXI Desktop Agent) is a general-purpose execution layer that enables natural language control of work computers. Users interact with their MUXI formation through existing channels (Slack, Teams, WhatsApp), and MDA executes tasks locally — browser automation, native app control, file operations, and system interactions.

MDA connects user machines to MUXI formations via Cloudflare Tunnel, creating a secure, NAT-traversing channel that requires zero network configuration. The architecture is simple: MDA receives instructions via SSE, executes locally using bundled MCP tools, and reports status back through the tunnel.

Two infrastructure models serve different market segments: a free-tier SaaS model for individuals using Cloudflare's free tunnels with application-layer auth, and an enterprise model with dedicated Cloudflare accounts, Access policies, and WorkOS integration.

------

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  MDA (Desktop Agent)                                            │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Agent Daemon                                             │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  Bundled MCP Tools                                  │  │  │
│  │  │  ├── Playwright (browser automation)                │  │  │
│  │  │  ├── macos-ui-automation / Windows-MCP (native GUI) │  │  │
│  │  │  ├── File system operations                         │  │  │
│  │  │  ├── AppleScript/JXA (macOS) / AutoIt (Windows)     │  │  │
│  │  │  └── [Extensible - additional MCPs]                 │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  Credential Store                                   │  │  │
│  │  │  ├── System password (for auth prompts)             │  │  │
│  │  │  ├── API keys                                       │  │  │
│  │  │  └── Stored in OS keychain (encrypted)              │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  MUXI Integration Layer                                   │  │
│  │  ├── HTTP MCP Server (exposes tools to formation)         │  │
│  │  ├── SSE Client (receives instructions)                   │  │
│  │  ├── cloudflared (tunnel subprocess)                      │  │
│  │  └── HMAC auth validation                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  UI Layer                                                 │  │
│  │  ├── Menu bar icon (status, quick actions)                │  │
│  │  ├── Execution mask (full-screen overlay while working)   │  │
│  │  └── Thinking pane (logs, progress, user input)           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Cloudflare Tunnel
                              ▼
                      ┌───────────────┐
                      │ MUXI Formation│
                      └───────────────┘
                              ▲
                              │
                      ┌───────────────┐
                      │ Slack/Teams/  │
                      │ WhatsApp/etc  │
                      └───────────────┘
                              ▲
                              │
                          [ User ]
```

### Component Breakdown

#### Agent Daemon

The core execution engine. Similar in concept to OpenCode, Claude Code, or CodeShip — an LLM-powered agent that can invoke tools to accomplish tasks.

**Responsibilities:**

- Receive instructions from MUXI formation via SSE
- Plan and execute multi-step tasks
- Invoke MCP tools for browser/GUI/file operations
- Report progress and results back to formation
- Handle errors and attempt alternative approaches

**Starting point:** Fork from [OpenWork](https://github.com/accomplish-ai/openwork) which already provides Electron shell + OpenCode CLI integration.

#### Bundled MCP Tools

Pre-configured MCP servers that ship with MDA:

| Tool                    | Platform       | Purpose                                   |
| ----------------------- | -------------- | ----------------------------------------- |
| Playwright MCP          | Cross-platform | Browser automation via accessibility tree |
| macos-ui-automation-mcp | macOS          | Native app control via Accessibility APIs |
| Windows-MCP             | Windows        | Native app control via UI Automation APIs |
| macos-automator-mcp     | macOS          | AppleScript/JXA execution (200+ recipes)  |
| File system MCP         | Cross-platform | File/folder operations                    |

**Native GUI automation details:**

macOS uses the Accessibility API (same framework as VoiceOver). Requires user to grant Accessibility permission to MDA in System Settings → Privacy & Security → Accessibility.

Windows uses UI Automation API (successor to Microsoft Active Accessibility). May require similar permissions depending on target applications.

#### Credential Store

Secure storage for sensitive data needed during automation:

| Credential      | Purpose                      | Storage                 |
| --------------- | ---------------------------- | ----------------------- |
| System password | Auto-fill sudo/admin prompts | OS Keychain (encrypted) |
| API keys        | Service authentication       | OS Keychain (encrypted) |
| OAuth tokens    | Service authentication       | OS Keychain (encrypted) |

**System password handling:**

- Collected during MDA setup (one-time)
- Used automatically when agent encounters system auth prompts
- Never transmitted to MUXI formation — stays local
- Reduces need for user input during execution to 2FA only

#### MUXI Integration Layer

The net-new code that differentiates MDA from a standalone agent:

**HTTP MCP Server:**

- Exposes bundled MCP tools to the remote MUXI formation
- Formation can invoke tools as if they were local
- HMAC validation on every request

**SSE Client:**

- Persistent connection to formation
- Receives instructions in real-time
- Handles reconnection on network issues

**cloudflared:**

- Bundled Cloudflare tunnel client (~25MB)
- Managed as subprocess
- Provides NAT-traversing inbound connectivity

#### UI Layer

Minimal UI focused on status and execution visibility:

**Menu bar icon:**

- Connection status (connected/disconnected)
- Recent activity
- Quick actions (pause, settings)

**Execution mask:**

- Full-screen transparent overlay during agent work
- Glowing border (Siri-style) indicates agent is active
- Thinking pane shows agent progress and logs

------

## Infrastructure Models

### Comparison

| Aspect             | SaaS (Individuals)             | Enterprise                       |
| ------------------ | ------------------------------ | -------------------------------- |
| Cloudflare account | Shared MUXI account            | Dedicated per-org account        |
| Tunnel URL         | `<tunnel-id>.cfargotunnel.com` | `<device-id>.<org>.mda.muxi.org` |
| Access policies    | None (free tier)               | IP allowlist + service tokens    |
| Authentication     | HMAC at app layer              | Cloudflare Access + HMAC         |
| Identity provider  | MUXI account                   | WorkOS → Customer SSO            |
| Cost to MUXI       | $0/user                        | ~$3/user/month                   |
| Price to customer  | Free / future premium          | $10/machine/month                |

### SaaS Model (Individuals)

**Tunnel provisioning:**

1. On first run, MDA calls Cloudflare API to create tunnel
2. Returns static tunnel ID (UUID) and credentials
3. Credentials stored locally in `~/.mda/tunnel-credentials.json`
4. Tunnel URL is permanent: `<tunnel-id>.cfargotunnel.com`

**Security model:**

- Tunnel URL obscurity (UUIDs are unguessable)
- HMAC request signing on every request
- Non-standard port for local MCP server

**Reinstall behavior:**

- Lost credentials = new tunnel provisioned
- Treated as new device (no credential backup complexity)

### Enterprise Model

**Per-organization isolation:**

- Dedicated Cloudflare account (`cloudflare+{org}@muxi.org`)
- Custom domain: `*.<org>.mda.muxi.org`
- Cloudflare Access policies restrict to MUXI formation IPs
- WorkOS OIDC integration for SSO

**Tunnel provisioning:**

1. MDA provisions tunnel in org's Cloudflare account
2. MUXI creates CNAME: `<device-id>.<org>.mda.muxi.org` → `<tunnel-id>.cfargotunnel.com`
3. Cloudflare Access rule applied to wildcard domain
4. Device registered in MUXI backend with org/user binding

**Security model (defense in depth):**

- Cloudflare Access (network layer): IP allowlist + service tokens
- HMAC signing (application layer): Every request signed
- WorkOS device authorization: IT admin can approve/revoke devices

### Pricing

**Enterprise:**

| Tier               | Price             |
| ------------------ | ----------------- |
| 1-200 machines     | $10/machine/month |
| 201-1,000 machines | $8/machine/month  |
| 1,000+ machines    | Contact sales     |

**SaaS:** Free tier at launch. Future premium features via Stripe.

**Margin:** ~70% enterprise (after Cloudflare Access), 100% SaaS free tier.

------

## User Experience

### Activation Model

**v1: Remote activation only**

No local chat interface at launch. Users invoke MDA through existing channels:

- Slack
- Microsoft Teams
- WhatsApp
- Any channel connected to MUXI formation

This simplifies v1:

- No new UI for users to learn
- Enterprise already has Slack/Teams deployed
- MUXI formation is the "brain," MDA is just the "hands"
- Fewer features to build and secure

Local chat window can be added in v2 as a convenience feature.

### Activation Flow

```
User (via Slack): "Check my email for messages from Sarah"
              ↓
MUXI Formation: [processes request, determines MDA needed]
              ↓
MDA receives instruction via SSE
              ↓
Is user at computer?
    ├── Yes (recent activity) → Show approval notification
    │         ↓
    │   Approval dialog with countdown (default 30s)
    │         ↓
    │   User approves OR countdown expires (auto-approve)
    │         ↓
    │   Agent executes
    │
    └── No (screen locked/idle) → Queue task
              ↓
        User returns → "You have 1 pending task. Run now?"
```

### Execution Mask

When agent is working, the entire screen is covered with a transparent overlay:

```
┌─────────────────────────────────────────────────────────────────┐
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓┌─────────────────────────────────────────────────────────────┐▓│
│▓│                                                             │▓│
│▓│      [Transparent view of desktop - agent working]          │▓│
│▓│                                                             │▓│
│▓│      User can see what agent is doing in real-time          │▓│
│▓│                                                             │▓│
│▓└─────────────────────────────────────────────────────────────┘▓│
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  THINKING PANE                                             │ │
│  │                                                            │ │
│  │  ✓ Opening Mail app...                                     │ │
│  │  ✓ Searching for messages from Sarah...                    │ │
│  │  ✓ Found 3 messages                                        │ │
│  │  ✓ Reading most recent...                                  │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ████████████████░░░░░░░░░░░░░░░░░░░░░░  Progress: 3/5 steps    │
│                                                                 │
│  [████ STOP ████]                          Press Cmd+Shift+Esc  │
│                                                                 │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
└─────────────────────────────────────────────────────────────────┘
  ↑ Glowing border (Siri-style animation)
```

**Visual elements:**

- Transparent center showing actual desktop
- Glowing animated border indicating "agent is active"
- Thinking pane with real-time agent logs and progress
- Progress bar showing task completion
- Stop button and keyboard shortcut always visible

### Input Lockout

During agent execution, user input is locked to prevent interference:

| Input                          | State During Execution     |
| ------------------------------ | -------------------------- |
| Mouse                          | Locked                     |
| Keyboard                       | Locked                     |
| Escape combo (`Cmd+Shift+Esc`) | Always works — stops agent |

**Rationale:** Agent is controlling mouse and keyboard. User input would cause conflicts and unpredictable behavior.

### 2FA / User Input Handling

When agent encounters 2FA or needs user input:

```
┌────────────────────────────────────────────────────────────────┐
│  THINKING PANE                                                 │
│                                                                │
│  ✓ Logging into Chase...                                       │
│  ✓ Entered credentials                                         │
│  ✓ 2FA required                                                │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  │  I need your 2FA code:                                   │  │
│  │                                                          │  │
│  │  [________________________]              0:47 remaining  │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Input unlock rules during 2FA:**

| Input                     | State                            |
| ------------------------- | -------------------------------- |
| Mouse                     | Locked                           |
| Keyboard (general)        | Locked                           |
| Keyboard (input box only) | Unlocked                         |
| Tab key                   | Disabled (prevents focus escape) |
| Escape combo              | Always works                     |

**Flow:**

1. Agent pauses execution
2. Input box appears in thinking pane with 60-second countdown
3. Keyboard unlocks for input box only
4. User types code, hits Enter
5. Keyboard locks again
6. Agent continues

**Timeout behavior:**

- If countdown reaches 0 with no input
- Agent attempts alternative approach or aborts gracefully
- User notified via original channel (Slack/Teams)

**Why 2FA is the only user input needed:**

- System password stored during setup (handles sudo/admin prompts)
- API keys and OAuth tokens stored in credential store
- 2FA codes are inherently real-time and can't be pre-stored

### Task Completion

When agent finishes:

1. Mask dismisses with fade animation
2. Toast notification: "Task complete: [summary]"
3. Full results sent back to user via original channel (Slack/Teams)

### State Summary

| State                | UI                                | User Input                       |
| -------------------- | --------------------------------- | -------------------------------- |
| Idle                 | Menu bar icon only                | Normal                           |
| Instruction received | Approval notification + countdown | Normal                           |
| Executing            | Full-screen mask + thinking pane  | Locked (except escape)           |
| 2FA needed           | Input box in thinking pane        | Keyboard unlocked for input only |
| Complete             | Toast notification                | Normal                           |
| User away + pending  | Badge on menu bar                 | Prompt on return                 |

------

## Technical Implementation

### MDA Client Components

| Component          | Technology                 | Notes                                       |
| ------------------ | -------------------------- | ------------------------------------------- |
| Shell              | Electron or Tauri          | Tauri preferred for smaller footprint       |
| Agent engine       | Fork of OpenCode or custom | Spawned as subprocess                       |
| MCP runtime        | Node.js                    | Hosts bundled MCP servers                   |
| Tunnel             | cloudflared                | Bundled binary, ~25MB                       |
| Credential storage | OS Keychain                | macOS Keychain / Windows Credential Manager |
| UI overlay         | Native window APIs         | Full-screen transparent window              |

### MUXI Backend Components

| Component               | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| Tunnel Provisioning API | Creates tunnels via Cloudflare API, manages CNAMEs   |
| Device Registry         | Maps device ID → tunnel URL → user → org             |
| Org Manager             | Manages per-org Cloudflare accounts, Access policies |
| WorkOS Integration      | OIDC config per org, SCIM webhook handler            |

### Platform-Specific MCP Tools

**macOS:**

- `macos-ui-automation-mcp` — Native GUI via Accessibility APIs
- `macos-automator-mcp` — AppleScript/JXA with 200+ pre-built recipes
- Requires: Accessibility permission in System Settings

**Windows:**

- `Windows-MCP` — Native GUI via UI Automation APIs
- `windows-desktop-automation` — AutoIt-based automation
- May require: UI Automation permissions for certain apps

**Cross-platform:**

- `Playwright MCP` — Browser automation
- File system operations

### Local Storage

```
~/.mda/
├── tunnel-credentials.json    # Cloudflare tunnel ID + secret
├── config.yml                 # Server URL, device ID, settings
└── logs/                      # Execution logs (rotated)

# Credentials in OS Keychain (not filesystem):
# - System password
# - API keys
# - OAuth tokens
```

### Installation Flow

**SaaS (Individuals):**

1. Download MDA for platform
2. Run installer, grant Accessibility permission
3. Login via MUXI account (browser OAuth)
4. Enter system password (stored in keychain)
5. MDA provisions Cloudflare tunnel
6. Registers tunnel URL with MUXI backend
7. Ready — user can invoke via Slack/etc

**Enterprise:**

1. Employee downloads MDA (or pushed via MDM)
2. Login via WorkOS → customer SSO
3. If device not pre-approved, IT admin receives approval request
4. Grant Accessibility permission
5. Enter system password (stored in keychain)
6. MDA provisions tunnel in org's Cloudflare account
7. CNAME created, Access policy applied
8. Ready

### Reinstall Handling

Same for both models:

- Reinstall with lost credentials = new device
- New tunnel provisioned, new device ID
- Enterprise: May require IT re-approval
- Old device shows as "disconnected" in admin dashboard

------

## Infrastructure Requirements

### Cloudflare Resources

| Resource  | SaaS                    | Enterprise       |
| --------- | ----------------------- | ---------------- |
| Tunnels   | Free (unlimited)        | Free (unlimited) |
| Access    | N/A                     | ~$3/user/month   |
| Bandwidth | ~50-200 MB/client/month | Same             |

### MUXI Backend

Minimal infrastructure:

- Tunnel provisioning API (Cloudflare API wrapper)
- Device registry database
- Org manager for enterprise accounts
- WorkOS integration endpoints

------

## Security Considerations

### Credential Security

- System password never leaves device
- Stored in OS Keychain with encryption
- Used only for local auth prompts
- MUXI formation never sees it

### Network Security

- All traffic through Cloudflare tunnel (encrypted)
- HMAC signing on every request
- Enterprise: Additional Cloudflare Access layer
- Non-standard local port reduces attack surface

### Permission Model

- User explicitly grants Accessibility permission
- User explicitly provides system password
- User approves each remote task (or auto-approve with countdown)
- Escape hatch always available to stop agent

### Enterprise Controls

- IT admin approves devices before activation
- Cloudflare Access logs all connection attempts
- Can revoke device access instantly
- Audit trail of all agent activity

------

## Timeline

| Phase               | Scope                                             | Target  |
| ------------------- | ------------------------------------------------- | ------- |
| Phase 1: Foundation | Agent daemon + MCP tools + manual tunnel          | Q1 2026 |
| Phase 2: SaaS       | Auto tunnel provisioning, MUXI auth, self-service | Q2 2026 |
| Phase 3: Enterprise | Per-org Cloudflare, WorkOS, Access policies       | Q3 2026 |
| Phase 4: Polish     | Auto-updates, analytics, MDM integration          | Q4 2026 |

------

## Success Metrics

| Metric                | Description                                    |
| --------------------- | ---------------------------------------------- |
| Adoption              | Active MDA installations, daily active devices |
| Reliability           | Tunnel uptime, reconnection success rate       |
| Task completion       | % of tasks completed successfully              |
| User input rate       | How often 2FA/input needed (lower is better)   |
| Enterprise conversion | Trial → paid, expansion within accounts        |
| Revenue               | MRR from enterprise subscriptions              |

------

## Future Considerations (v2+)

- **Local chat window** — Convenience for power users
- **Voice input** — "Hey MDA, the code is 482910"
- **Mobile companion app** — Chat with MDA from phone while it works
- **Linux support** — AT-SPI2 based GUI automation
- **Screen region mode** — Agent works in partial screen, user keeps rest
- **Scheduled tasks** — "Every morning, check my calendar and summarize"