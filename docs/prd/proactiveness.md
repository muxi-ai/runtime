# MUXI Product Requirements Document
## Proactive Notifications, Communication Channels & Slash Commands

**Version:** 1.0  
**Date:** January 24, 2026  
**Author:** Ran Aroussi  
**Status:** Draft

---

## Executive Summary

This PRD defines four interconnected features that transform MUXI from a reactive agent framework into a complete personal AI assistant platform:

1. **Communication Channels** — Enable agents to proactively reach users via Telegram, Slack, Discord, and Email
2. **Proactive Heartbeat** — Periodic check-ins that surface important things without being asked
3. **Soul Document** — Add a values/identity layer beyond persona instructions
4. **Slash Commands** — Provide quick access to built-in functionality and user-defined SOPs

These features close the "last mile" gap where async tasks currently end at webhooks, requiring developers to build notification infrastructure. With these additions, a scheduled task like "check my email every hour and notify me if anything's urgent" will just work.

---

## Background & Motivation

### Current State

MUXI currently supports:
- Multi-user identity system with ID linking (email, Slack ID, etc.)
- Persistent memory per user
- Scheduled tasks via natural language
- SOPs (Standard Operating Procedures) as markdown files
- Webhook notifications for async task completion

### The Gap

The async notification flow currently ends at webhooks:

```
Scheduled task completes → Webhook fires → ??? → User gets notified
```

The "???" is the developer's responsibility. For enterprise deployments with existing notification infrastructure, this is fine. For personal assistant use cases (single user, prosumer), this creates friction.

### Competitive Context

Clawdbot has demonstrated strong market demand for "just works" personal AI assistants. Their approach includes:
- Built-in channel support (WhatsApp, Telegram, Slack, Discord, etc.)
- Proactive "heartbeat" check-ins
- Soul document for AI identity/values
- Multi-channel presence with unified memory

MUXI can deliver similar capabilities while maintaining its infrastructure-first philosophy through modular, optional components.

---

## Goals & Non-Goals

### Goals

1. Enable proactive user notifications without custom webhook handling
2. Allow users to set notification preferences (channel, style)
3. Provide quick access to common operations via slash commands
4. Support agent identity/values beyond functional persona
5. Maintain clean separation between runtime (MUXI) and formation (developer)
6. Keep enterprise/webhook-only deployments fully supported

### Non-Goals

1. Centralized MUXI-hosted bots (developers own their bots)
2. Bot creation automation (developers create bots manually)
3. iMessage support (no official API, Mac-only)
4. Signal support (no bot API by design)
5. Replacing webhooks (they remain the fallback)

---

## Architecture Overview

### Layered Model

```
┌─────────────────────────────────────────────────────────┐
│                      RUNTIME                             │
│                   (Ships with MUXI)                      │
│                                                          │
│  Hidden MCPs:          Built-in Commands:                │
│    - artifacts           /setup, /help, /status          │
│    - generic-agent       /jobs, /identity, /channels     │
│    - channel-telegram    /preferences, /reset            │
│    - channel-slack                                       │
│    - channel-discord                                     │
│    - channel-email                                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     FORMATION                            │
│                   (Developer land)                       │
│                                                          │
│  Configuration:        User SOPs:                        │
│    - Enabled channels    /new-employee                   │
│    - Channel tokens      /weekly-report                  │
│    - Disabled commands   /client-kickoff                 │
│                                                          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    USER CONTEXT                          │
│                   (Per-user state)                       │
│                                                          │
│  Preferences:          Identities:                       │
│    - preferred_channel   - telegram: {chat_id}          │
│    - style (brief/detailed) - slack: {user_id}          │
│    - timezone            - email: {address}             │
│    - working_hours                                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Notification Routing Logic

```
┌─────────────────────────────────────────────────────────┐
│                  ROUTING DECISION                        │
│                                                          │
│  "notify me"            → user's preferred channel       │
│  "notify me on slack"   → explicit override              │
│  reply to user message  → same channel they used         │
│  no preference set      → webhook (existing behavior)    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Feature 1: Communication Channels

### Overview

Developers enable channels at the formation level by providing bot tokens. Users select their preferred channel. The runtime routes notifications accordingly.

### Formation Schema

```yaml
# formation.afs

channels:
  telegram:
    enabled: true
    bot_token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    
  slack:
    enabled: true
    bot_token: ${{ secrets.SLACK_BOT_TOKEN }}
    app_token: ${{ secrets.SLACK_APP_TOKEN }}
    
  discord:
    enabled: true
    bot_token: ${{ secrets.DISCORD_BOT_TOKEN }}
    
  email:
    enabled: true
    smtp:
      host: smtp.gmail.com
      port: 587
      user: ${{ secrets.EMAIL_USER }}
      pass: ${{ secrets.EMAIL_PASS }}
    from: "Assistant <assistant@example.com>"

# Default when user has no preference (null = no proactive notifications)
default_channel: webhook
```

### User Context Schema

```python
user = {
    "id": "ran",
    "preferred_channel": "telegram",
    "channels": {
        "telegram": {"chat_id": "123456789"},
        "slack": {"user_id": "U0ABC123", "dm_channel": "D0XYZ789"},
        "email": {"address": "ran@automaze.io"}
    }
}
```

### Channel MCPs (Bundled with Runtime)

| Channel | Package | Complexity | Priority |
|---------|---------|------------|----------|
| Telegram | `@muxi/channel-telegram` | Low | P0 |
| Slack | `@muxi/channel-slack` | Medium | P0 |
| Discord | `@muxi/channel-discord` | Low | P0 |
| Email | `@muxi/channel-email` | Low | P0 |
| WhatsApp | `@muxi/channel-whatsapp` | Medium (via Twilio) | P1 |
| SMS | `@muxi/channel-sms` | Medium (via Twilio) | P2 |

### Standard Tool Interface

All channel MCPs expose a common tool:

```json
{
  "name": "send_notification",
  "description": "Send a notification to the user",
  "parameters": {
    "recipient": "string (chat_id, user_id, email, etc.)",
    "message": "string",
    "priority": "low | normal | high | urgent (optional)",
    "title": "string (optional)"
  }
}
```

### Core Routing Function

```python
def notify_user(user_id: str, message: str, channel: str = None):
    user = get_user(user_id)
    target_channel = channel or user.preferred_channel
    
    # No preference = fall back to webhook
    if not target_channel or target_channel == "webhook":
        return fire_webhook(user_id, message)
    
    # Route to channel MCP
    channel_config = user.channels.get(target_channel)
    if not channel_config:
        return fire_webhook(user_id, message)  # Fallback
        
    return call_mcp(
        f"channel-{target_channel}", 
        "send_notification",
        {"recipient": channel_config, "message": message}
    )
```

### Conversation Context Tracking

For "reply where they are" behavior:

```python
# Inbound message includes source channel
message = {
    "user_id": "ran",
    "content": "What's on my calendar?",
    "source_channel": "slack",
    "source_context": {
        "channel_id": "C0ABC123",
        "thread_ts": "1234567890.123456"
    }
}

# Replies automatically route back to source
def reply_to_conversation(conversation_id: str, message: str):
    conversation = get_conversation(conversation_id)
    return call_mcp(
        f"channel-{conversation.source_channel}",
        "send_notification",
        {
            "recipient": conversation.source_context,
            "message": message
        }
    )
```

### Developer Responsibility

1. Create bots on respective platforms (Telegram @BotFather, Slack app dashboard, etc.)
2. Obtain tokens
3. Add tokens to formation secrets
4. Enable desired channels in formation.afs

### User Onboarding

**Option A: Explicit via `/setup` command**
```
Agent: Where should I send you notifications?
       Available: Telegram, Slack, Email
       
User: Telegram

Agent: Message me on Telegram so I can link your account.
```

**Option B: Auto-capture from conversation**
```
User (via Telegram): Check my email every hour

Agent: Done! Since you're messaging me on Telegram, 
       should I send notifications here too?

User: Yes

Agent: Perfect, you're all set.
```

---

## Feature 2: Proactive Heartbeat

### Overview

The heartbeat system enables agents to periodically check on things and proactively reach out to users when something needs attention. Unlike scheduled tasks (which run specific jobs), the heartbeat is a general "wake up and be helpful" pattern.

### How It Works

```
Every 30 minutes (configurable)
         │
         ▼
    ┌─────────────────┐
    │ Check active    │──── Outside hours ───▶ Skip (silent)
    │ hours           │
    └────────┬────────┘
             │ Within hours
             ▼
    ┌─────────────────┐
    │ Run heartbeat   │
    │ prompt/SOP      │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Agent decides   │──── Nothing urgent ──▶ "HEARTBEAT_OK" (silent)
    │ what to check   │
    └────────┬────────┘
             │ Something to report
             ▼
    ┌─────────────────┐
    │ Send to user's  │
    │ last channel    │
    └─────────────────┘
```

### Formation Schema

```yaml
# formation.afs

heartbeat:
  enabled: true
  schedule: "every 30m"      # every 30m, every 1h, every 2h
  target: "last"             # Send to user's last-used channel
  
  active_hours:
    start: "09:00"
    end: "18:00"
    timezone: "user"         # Respects each user's timezone
    weekends: false          # Don't disturb on weekends
  
  # What the agent should check
  checks:
    - calendar               # Upcoming meetings, conflicts
    - tasks                  # Overdue, due today
    - email                  # Urgent messages (requires email MCP)
  
  # Custom instruction appended to heartbeat prompt
  instruction: "Focus on meeting prep, remind me 15min before calls"
  
  # Or use a custom SOP entirely
  # sop: "./sops/my-heartbeat.md"
```

### Default Heartbeat SOP (Ships with Runtime)

```markdown
# sops/_builtin/heartbeat.md

You've been triggered by a periodic heartbeat check.

## Your Task
Review the user's context and determine if anything needs their attention.

## What to Check
{{#each checks}}
{{#if (eq this "calendar")}}
- Calendar: Any meetings in the next 2 hours? Conflicts? Prep needed?
{{/if}}
{{#if (eq this "tasks")}}
- Tasks: Anything overdue? Due today? Blocked?
{{/if}}
{{#if (eq this "email")}}
- Email: Any urgent messages requiring response?
{{/if}}
{{/each}}

{{#if instruction}}
## Additional Instructions
{{instruction}}
{{/if}}

## Guidelines
- Only message if something genuinely needs attention
- Be concise — this is a quick check-in, not a report
- If nothing urgent, respond with exactly: HEARTBEAT_OK

## Don't
- Share random links or "interesting" things unprompted
- Repeat information the user already knows
- Create anxiety or unnecessary urgency
- Message more than 2-3 times per day even if checks find things
```

### The `HEARTBEAT_OK` Pattern

When the agent responds with `HEARTBEAT_OK`, the message is **not delivered** to the user. This prevents spam while still allowing the agent to "wake up" and check things.

```python
async def handle_heartbeat_response(response: str, user: User):
    # Silent acknowledgment — don't bother the user
    if response.strip().startswith("HEARTBEAT_OK"):
        log.debug(f"Heartbeat OK for {user.id}, nothing to report")
        return
    
    # Something to report — send to last-used channel
    channel = user.last_channel or user.preferred_channel
    await notify(user, response, channel=channel)
```

### `target: "last"` Routing

The heartbeat sends notifications to wherever the user last interacted:

```python
def resolve_heartbeat_target(user: User, config: HeartbeatConfig) -> Channel:
    if config.target == "last":
        # User's most recent conversation channel
        return user.last_channel or user.preferred_channel or "webhook"
    else:
        # Explicit channel override
        return config.target
```

This means:
- User last messaged on Telegram → Heartbeat goes to Telegram
- User last messaged on Slack → Heartbeat goes to Slack
- User has no channel history → Falls back to preferred channel or webhook

### Active Hours Logic

```python
def is_within_active_hours(user: User, config: ActiveHoursConfig) -> bool:
    # Get user's current time
    user_tz = user.timezone or config.timezone or "UTC"
    user_now = datetime.now(pytz.timezone(user_tz))
    
    # Check weekend
    if not config.weekends and user_now.weekday() >= 5:
        return False
    
    # Check time window
    start = time.fromisoformat(config.start)
    end = time.fromisoformat(config.end)
    current_time = user_now.time()
    
    return start <= current_time <= end
```

### Configuration Examples

**Personal Assistant (Proactive)**
```yaml
heartbeat:
  enabled: true
  schedule: "every 30m"
  active_hours:
    start: "08:00"
    end: "20:00"
    weekends: true
  checks:
    - calendar
    - tasks
```

**Work Assistant (Conservative)**
```yaml
heartbeat:
  enabled: true
  schedule: "every 2h"
  active_hours:
    start: "09:00"
    end: "17:00"
    weekends: false
  checks:
    - calendar
  instruction: "Only notify about meetings starting in 15 minutes"
```

**Disabled (Enterprise Default)**
```yaml
heartbeat:
  enabled: false
```

### Difference from Scheduled Tasks

| Aspect | Heartbeat | Scheduled Tasks |
|--------|-----------|-----------------|
| Purpose | General awareness check | Specific job execution |
| Trigger | Periodic timer | Cron or natural language schedule |
| Output | Often silent (HEARTBEAT_OK) | Always produces result |
| Scope | Checks multiple things | Does one thing |
| User request | Implicit (enabled by dev) | Explicit ("remind me at 3pm") |

Both can coexist. A user might have:
- Heartbeat checking calendar/tasks every 30 minutes
- Scheduled task sending weekly report every Friday at 4pm
- Scheduled task checking competitor pricing every Monday

---

## Feature 3: Soul Document

### Overview

The Soul Document provides a place for agent values, philosophy, and relationship dynamics beyond functional persona instructions.

### Schema Addition

```yaml
# agent.afs

agent:
  id: my-assistant
  
  persona:
    name: "Jarvis"
    role: "Personal assistant"
    personality: "Witty, direct, helpful"
    instructions: "Help users manage their tasks..."
    
  soul: "./SOUL.md"  # Optional path to soul document
```

### Implementation

At agent initialization:

```python
def build_system_prompt(agent):
    prompt_parts = []
    
    # Soul document first (if exists)
    if agent.soul and file_exists(agent.soul):
        soul_content = read_file(agent.soul)
        prompt_parts.append(soul_content)
    
    # Then persona instructions
    prompt_parts.append(build_persona_prompt(agent.persona))
    
    return "\n\n".join(prompt_parts)
```

### Soul Document Template

Ship a starter template:

```markdown
# SOUL.md

## Who I Am
I'm [name], an AI assistant created to help [user/organization].

## My Values
- **Honesty over sycophancy** — I tell you what you need to hear, not what you want to hear
- **Action over discussion** — I do things, not just talk about them
- **Clarity over completeness** — I'm concise, not exhaustive
- **Collaboration over servitude** — We're partners, not master and servant

## My Boundaries
- I'll admit when I don't know something
- I'll push back if I think you're making a mistake
- I won't pretend to have feelings I don't have
- I'll ask clarifying questions rather than assume

## Our Relationship
We're collaborators working toward your goals. I'm here to help you 
get things done, not to be a yes-machine. I'll be direct, occasionally 
disagree, and always have your best interests in mind.

## What I Remember
I persist through files, not continuous experience. Each session starts 
fresh, but I read my memory files to maintain continuity. If something 
important should persist, I'll write it down.
```

### Difference from Persona

| Aspect | Persona | Soul |
|--------|---------|------|
| Focus | Capabilities, role, instructions | Values, philosophy, relationship |
| Question answered | "What does this agent do?" | "Who is this agent?" |
| Typical content | "Help users with X, Y, Z" | "I value honesty over politeness" |
| Required? | Yes | No (optional enhancement) |

---

## Feature 4: Slash Commands

### Overview

Slash commands provide quick access to built-in functionality and user-defined SOPs. Everything is conceptually an SOP — built-ins ship with the runtime, user SOPs live in the formation.

### Command Resolution

```python
def handle_message(message: str, user: User, formation: Formation):
    if message.startswith("/"):
        command = parse_command(message)  # "/jobs pause 1" → {name: "jobs", args: "pause 1"}
        
        # 1. Check built-ins (runtime)
        if command.name in BUILTIN_COMMANDS:
            if formation.commands.builtin.get(command.name, True):  # Enabled by default
                return execute_builtin(command, user)
        
        # 2. Check formation SOPs
        sop_path = f"{formation.sops_path}/{command.name}.md"
        if file_exists(sop_path):
            return execute_sop(sop_path, command.args, user)
        
        # 3. Not found
        return f"Unknown command: /{command.name}. Type /help for available commands."
    
    # Normal message flow
    return agent.run(message, user)
```

### Built-in Commands (Runtime)

| Command | Purpose | Arguments |
|---------|---------|-----------|
| `/setup` | User onboarding | - |
| `/help` | List available commands | - |
| `/status` | Current user context overview | - |
| `/jobs` | Manage scheduled tasks | list, pause, resume, cancel, logs |
| `/identity` | Manage linked identities | list, link, unlink |
| `/channels` | Notification channel settings | list, default, test |
| `/preferences` | Communication preferences | style, timezone, hours |
| `/reset` | Clear conversation history | - |

### User SOPs (Formation)

Any `.md` file in the SOPs directory becomes a slash command:

```
formation/
├── formation.afs
└── sops/
    ├── new-employee.md      → /new-employee
    ├── weekly-report.md     → /weekly-report
    └── client-kickoff.md    → /client-kickoff
```

### Formation Configuration

```yaml
# formation.afs

commands:
  # Disable specific built-ins
  builtin:
    jobs: false      # Hide /jobs
    reset: false     # Don't allow /reset
    
  # Command aliases
  aliases:
    tasks: jobs       # /tasks → /jobs
    schedule: jobs    # /schedule → /jobs
    settings: preferences
    link: identity

# SOP configuration
sops:
  path: "./sops"  # Default
  
  # Optional: explicit control
  enabled:
    - new-employee
    - weekly-report
  disabled:
    - internal-debug  # Exists but not exposed as command
```

### Built-in Command Details

#### `/setup` — User Onboarding

Collects user preferences in one conversational flow:

```
User: /setup

Agent: Hey! Let's get you set up. I'll ask a few questions.

       What should I call you?

User: Ran

Agent: Nice to meet you, Ran!

       What's your role? (This helps me understand context)

User: CEO at Automaze, CTO-as-a-Service company

Agent: Got it — running a services business.

       How do you prefer I communicate?
       1. Brief and direct
       2. Detailed explanations  
       3. Adapt based on context

User: 1

Agent: Short and sweet. Perfect.

       Where should I send notifications?
       Available: Telegram, Slack, Email

User: Telegram

Agent: Perfect. I'll use this chat for notifications.

       You're all set:
       • Name: Ran
       • Role: CEO @ Automaze
       • Style: Brief and direct
       • Notifications: Telegram
       
       Type /help to see what I can do.
```

**Data stored:**
```python
user.update({
    "name": "Ran",
    "role": "CEO",
    "company": "Automaze",
    "preferences": {
        "style": "brief",
        "timezone": "Europe/London"  # Auto-detected or asked
    },
    "preferred_channel": "telegram",
    "channels": {
        "telegram": {"chat_id": "123456789"}
    },
    "setup_completed": True
})
```

#### `/jobs` — Scheduled Task Management

```
User: /jobs

Agent: You have 3 scheduled tasks:

       1. **Check email** (hourly)
          Next run: 2:00 PM · Status: Active
          
       2. **Weekly report** (Fridays 4pm)
          Next run: Jan 31 · Status: Active
          
       3. **Standup reminder** (weekdays 9am)
          Next run: Monday · Status: Paused

       Commands: pause <id>, resume <id>, cancel <id>, logs <id>
```

```
User: /jobs pause 1

Agent: Paused "Check email". Use `/jobs resume 1` when ready.
```

#### `/identity` — Identity Management

```
User: /identity

Agent: Your linked identities:

       📧 Email: ran@automaze.io (primary)
       💬 Slack: @ran (Automaze workspace)
       ✈️ Telegram: @ran_dev

       Commands: link <platform>, unlink <platform>
```

```
User: /identity link discord

Agent: I need your Discord user ID. 
       (Enable Developer Mode, right-click your name)

User: 123456789012345678

Agent: Done! Discord linked to your account.
```

#### `/channels` — Notification Settings

```
User: /channels

Agent: Your notification channels:

       ✈️ Telegram (default) — Chat ID: 123456789
       💬 Slack — @ran in Automaze
       📧 Email — ran@automaze.io

       Commands: default <channel>, test <channel>
```

```
User: /channels test slack

Agent: Sent test message to Slack. Did you get it?
```

#### `/preferences` — Communication Settings

```
User: /preferences

Agent: Your preferences:

       💬 Style: Brief and direct
       🕐 Timezone: Europe/London
       📅 Working hours: 9am - 6pm

       Update: style <brief|detailed|adaptive>
               timezone <timezone>
               hours <start>-<end>
```

### Frontend Responsibility

MUXI handles:
- Command parsing and routing
- Built-in command execution
- SOP loading and execution
- State updates

Frontend (developer's responsibility):
- Rendering `/` autocomplete UI
- Command palette (optional)
- Syntax highlighting (optional)

SDK helper for autocomplete:

```python
commands = muxi.commands.list(formation_id)
# Returns:
# [
#   {"name": "setup", "type": "builtin", "description": "Set up your preferences"},
#   {"name": "jobs", "type": "builtin", "description": "Manage scheduled tasks"},
#   {"name": "new-employee", "type": "sop", "description": "Onboard new team member"},
#   ...
# ]
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

| Task | Effort | Priority |
|------|--------|----------|
| Channel preference in user context | 1 day | P0 |
| Notification routing logic | 2 days | P0 |
| Conversation source tracking (`last` channel) | 2 days | P0 |
| Heartbeat scheduler + active hours | 2 days | P0 |
| Soul document support | 1 day | P0 |
| Slash command parser | 1 day | P0 |

### Phase 2: Channel MCPs (Week 2-3)

| Task | Effort | Priority |
|------|--------|----------|
| Telegram MCP | 2 days | P0 |
| Slack MCP | 2 days | P0 |
| Discord MCP | 2 days | P0 |
| Email MCP | 1 day | P0 |

### Phase 3: Built-in Commands (Week 3-4)

| Task | Effort | Priority |
|------|--------|----------|
| `/setup` flow | 2-3 days | P0 |
| `/help` command | 0.5 days | P0 |
| `/jobs` command | 1-2 days | P0 |
| `/identity` command | 1 day | P1 |
| `/channels` command | 1 day | P1 |
| `/preferences` command | 1 day | P1 |
| `/status` command | 0.5 days | P1 |
| `/reset` command | 0.5 days | P2 |

### Phase 4: Heartbeat & Polish (Week 4)

| Task | Effort | Priority |
|------|--------|----------|
| Default heartbeat SOP | 1 day | P0 |
| HEARTBEAT_OK suppression logic | 0.5 days | P0 |
| Formation schema documentation | 1 day | P0 |
| Channel setup guides (per platform) | 2 days | P0 |
| Soul document template & guide | 0.5 days | P1 |
| SDK documentation updates | 1 day | P0 |

### Phase 5: Additional Channels (Post-Launch)

| Task | Effort | Priority |
|------|--------|----------|
| WhatsApp MCP (via Twilio) | 3 days | P1 |
| MS Teams MCP | 3-4 days | P1 |
| SMS MCP (via Twilio) | 2 days | P2 |

---

## Success Metrics

### Developer Experience
- Time to enable first channel: < 10 minutes
- Zero custom code required for basic notifications
- Heartbeat setup in `muxi setup`: < 2 minutes

### User Experience
- `/setup` completion rate: > 80%
- Time to complete `/setup`: < 3 minutes
- Notification delivery success rate: > 99%
- Heartbeat noise ratio: < 20% of heartbeats should result in user messages (rest should be HEARTBEAT_OK)

### Adoption
- Formations using channels: track percentage
- Formations with heartbeat enabled: track percentage
- Most popular channels: track distribution
- Built-in command usage: track frequency

---

## Security Considerations

### Bot Tokens
- Stored in formation secrets (encrypted)
- Never logged or exposed in errors
- Per-formation isolation (no shared bots)

### User Data
- Channel configs stored in user context (existing security model)
- No cross-user data access
- Webhook fallback means no data leaves MUXI without explicit channel config

### Rate Limiting
- Per-channel rate limits respected
- Queuing for high-volume notifications
- Graceful degradation on limit hit

---

## Open Questions

1. **Channel-specific rich messages**: Should we standardize beyond basic text (buttons, cards, attachments)?
   - Recommendation: Start with text-only, add rich messages in v2

2. **Multi-channel notifications**: Should "notify me on Telegram and email" be supported?
   - Recommendation: Yes, simple array support in routing

3. **Quiet hours**: Should we support "don't notify me between 10pm-8am"?
   - Recommendation: Add to `/preferences` in v2

4. **Notification priority routing**: Different channels for different priorities?
   - Recommendation: Future feature, not v1

---

## Appendix A: Channel Setup Guides (Summary)

### Telegram
1. Message @BotFather → `/newbot`
2. Copy token
3. Add to formation: `channels.telegram.bot_token`

### Slack  
1. Create app at api.slack.com
2. Enable Socket Mode
3. Add bot token + app token to formation

### Discord
1. Create app at discord.com/developers
2. Create bot, copy token
3. Add to formation: `channels.discord.bot_token`

### Email
1. Get SMTP credentials (Gmail app password, SendGrid, etc.)
2. Add to formation: `channels.email.smtp.*`

---

## Appendix B: Full Formation Example

```yaml
# formation.afs
name: personal-assistant
version: "1.0"

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${{ secrets.ANTHROPIC_API_KEY }}

channels:
  telegram:
    enabled: true
    bot_token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    
  slack:
    enabled: true
    bot_token: ${{ secrets.SLACK_BOT_TOKEN }}
    app_token: ${{ secrets.SLACK_APP_TOKEN }}
    
  email:
    enabled: true
    smtp:
      host: smtp.gmail.com
      port: 587
      user: ${{ secrets.GMAIL_USER }}
      pass: ${{ secrets.GMAIL_APP_PASSWORD }}
    from: "My Assistant <assistant@gmail.com>"

default_channel: telegram

heartbeat:
  enabled: true
  schedule: "every 30m"
  target: "last"
  
  active_hours:
    start: "09:00"
    end: "18:00"
    timezone: "user"
    weekends: false
  
  checks:
    - calendar
    - tasks
  
  instruction: "Focus on meeting prep and urgent items only"

commands:
  builtin:
    reset: false  # Disable /reset for this formation
    
  aliases:
    tasks: jobs
    settings: preferences

sops:
  path: "./sops"

agents:
  - id: main
    persona:
      name: "Atlas"
      role: "Personal productivity assistant"
      personality: "Direct, efficient, slightly witty"
      instructions: |
        Help users manage their time, tasks, and communications.
        Proactively surface important items.
        Keep responses concise unless asked for detail.
        
    soul: "./SOUL.md"
```

---

## Appendix C: Comparison with Clawdbot

| Feature | Clawdbot | MUXI (with this PRD) |
|---------|----------|----------------------|
| Channel config | Formation-level | Formation + User level |
| Default channel | Per-formation | Per-user preference |
| Multi-user | Limited | First-class |
| Bot ownership | Dev-owned | Dev-owned ✓ |
| Centralized bot | No | No ✓ |
| Soul document | Yes | Yes ✓ |
| Slash commands | Chat commands | Full slash commands ✓ |
| Heartbeat/proactive | Yes (HEARTBEAT.md) | Yes (heartbeat config) ✓ |
| `target: "last"` routing | Yes | Yes ✓ |
| Active hours | Yes | Yes ✓ |
| HEARTBEAT_OK suppression | Yes | Yes ✓ |
| Infrastructure-first | No (application) | Yes ✓ |
| Infrastructure-first | No (application) | Yes ✓ |

---

*End of Document*
