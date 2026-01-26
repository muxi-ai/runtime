# MUXI PRD: Developer Onboarding & CLI

**Version:** 1.0  
**Date:** January 24, 2026  
**Status:** Draft

---

## Summary

Define the developer experience from `pip install muxi` to a running agent. Introduce `muxi setup` as the unified entry point that guides developers through formation creation, LLM configuration, and channel setup.

---

## Two Onboarding Paths

| Path | Who | When | Goal |
|------|-----|------|------|
| `muxi setup` | Developer | After install | Working formation with channels |
| `/setup` | End user | First interaction | Preferences, identity, notifications |

This PRD covers the developer path. User onboarding (`/setup`) is covered in the Proactive Notifications PRD.

---

## Current State

```
pip install muxi
    │
    ▼
"Watch this video: ..."
"Run: muxi new formation"
    │
    ▼
Formation wizard
    │
    ▼
??? (figure out channels, secrets, deployment)
```

**Problems:**
- No unified entry point
- Channel setup is manual/undocumented
- Secrets management unclear
- No validation or diagnostics

---

## Proposed Flow

```
pip install muxi
    │
    ▼
muxi setup
    │
    ├──────────────────────────────────────┐
    │                                      │
    ▼                                      ▼
[First time]                         [Existing install]
    │                                      │
    ▼                                      ▼
Formation + LLM + Channels           Setup menu:
    │                                 ├─ Add channel
    ▼                                 ├─ Update LLM
Test + Next steps                     ├─ Manage secrets
                                      └─ Run diagnostics
```

---

## `muxi setup` Wizard

### Fresh Install

```
$ muxi setup

╭─────────────────────────────────────────╮
│         Welcome to MUXI Setup           │
╰─────────────────────────────────────────╯

Checking environment...
  ✓ Python 3.11+
  ✓ MUXI v0.1.0

No existing formation found.

? What would you like to do?
  › Create a new formation (recommended)
    Import existing formation
    Configure global settings
```

### Step 1: Formation Basics

```
──────────────────────────────────────────
Creating new formation...

? Formation name: my-assistant
? Description: Personal productivity assistant
```

### Step 2: LLM Configuration

```
──────────────────────────────────────────
LLM Configuration

? Provider:
  › Anthropic (recommended)
    OpenAI
    OpenRouter
    Local (Ollama, llama.cpp)
    Other

? API Key: sk-ant-••••••••••••
  ✓ Key validated (claude-sonnet-4-20250514 available)

? Default model: 
  › claude-sonnet-4-20250514 (recommended)
    claude-opus-4-20250514
    claude-haiku-4-20250514
```

### Step 3: Communication Channels

```
──────────────────────────────────────────
Communication Channels (optional)

Channels let your agent send proactive notifications.
You can skip this and add channels later.

? Set up channels now?
  › Yes, guide me through it
    Skip for now

──────────────────────────────────────────
Telegram Setup

  1. Open Telegram and message @BotFather
  2. Send /newbot
  3. Choose a name and username for your bot
  4. Copy the token BotFather gives you

? Bot token: 123456789:ABCdef••••••••••
  ✓ Token valid
  ✓ Bot name: MyAssistantBot

? Enable Telegram? Yes

──────────────────────────────────────────
Other Channels

? Enable Slack?  › No (set up later)
? Enable Discord? › No (set up later)
? Enable Email?   › No (set up later)
```

### Step 4: Proactive Check-ins

```
──────────────────────────────────────────
Proactive Check-ins (optional)

Your agent can periodically check if there's anything 
worth telling users about — like a good assistant 
who surfaces important things without being asked.

? Enable proactive check-ins?
  › Yes (recommended for personal assistants)
    No (user must initiate all interactions)

──────────────────────────────────────────
Check-in Settings

? How often should the agent check in?
  › Every 30 minutes (recommended)
    Every hour
    Every 2 hours
    Custom

? Active hours (agent won't disturb outside these):
  Start: 9:00 AM
  End:   6:00 PM
  
? Respect weekends?
  › Yes, stay quiet on weekends
    No, same schedule every day

──────────────────────────────────────────
What should the agent check?

  ☑ Calendar (upcoming meetings, conflicts)
  ☑ Tasks (overdue, due today)
  ☐ Email (urgent messages) — requires email MCP
  ☐ Custom checklist

? Add a custom instruction? (optional)
  > Focus on meeting prep, remind me 15min before calls
```

### Step 5: Test & Finish

```
──────────────────────────────────────────
Testing...

  ✓ LLM connection successful
  ✓ Telegram bot responding
  ✓ Heartbeat configured (every 30m, 9am-6pm weekdays)
  ✓ Formation valid

──────────────────────────────────────────

✓ Formation created: ./my-assistant/

Files created:
  my-assistant/
  ├── formation.afs
  ├── .env
  └── sops/
      └── (empty, add your SOPs here)

──────────────────────────────────────────
Next Steps

  cd my-assistant
  
  muxi serve        # Run locally
  muxi chat         # Test in terminal
  muxi deploy       # Deploy to cloud

Documentation: https://docs.muxi.sh
Join Discord:   https://discord.gg/muxi
```

---

### Generated Formation (Example)

After completing setup with Telegram and proactive check-ins enabled:

```yaml
# formation.afs
name: my-assistant
version: "1.0"

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${{ env.ANTHROPIC_API_KEY }}

channels:
  telegram:
    enabled: true
    bot_token: ${{ env.TELEGRAM_BOT_TOKEN }}

heartbeat:
  enabled: true
  schedule: "every 30m"
  target: "last"  # Send to user's last-used channel
  
  active_hours:
    start: "09:00"
    end: "18:00"
    timezone: "user"
    weekends: false
  
  checks:
    - calendar
    - tasks
  
  instruction: "Focus on meeting prep, remind me 15min before calls"
```

---

### Existing Install

```
$ muxi setup

╭─────────────────────────────────────────╮
│           MUXI Setup                    │
╰─────────────────────────────────────────╯

Found existing formation: ./my-assistant/

? What would you like to do?
  › Add a channel
    Configure proactive check-ins
    Update LLM configuration
    Manage secrets
    Run diagnostics
    Create new formation
```

---

## Command Reference

### Setup Commands

| Command | Description |
|---------|-------------|
| `muxi setup` | Interactive setup wizard |
| `muxi setup --minimal` | Formation + LLM only, skip channels |
| `muxi setup --channel telegram` | Add specific channel to existing formation |
| `muxi setup --from template` | Start from a template formation |

### Formation Commands

| Command | Description |
|---------|-------------|
| `muxi new formation` | Create new formation (wizard) |
| `muxi new agent` | Add agent to existing formation |
| `muxi new sop` | Create new SOP file |
| `muxi validate` | Validate formation.afs |

### Configuration Commands

| Command | Description |
|---------|-------------|
| `muxi config` | View current configuration |
| `muxi config edit` | Open formation.afs in editor |
| `muxi config channels` | List/manage channels |
| `muxi config secrets` | List/manage secrets |
| `muxi config llm` | Update LLM settings |

### Runtime Commands

| Command | Description |
|---------|-------------|
| `muxi serve` | Run agent locally |
| `muxi serve --port 8080` | Run on specific port |
| `muxi chat` | Interactive terminal chat |
| `muxi chat --user alice` | Chat as specific user |

### Diagnostics Commands

| Command | Description |
|---------|-------------|
| `muxi doctor` | Full diagnostic check |
| `muxi doctor --fix` | Auto-fix common issues |
| `muxi logs` | View agent logs |
| `muxi logs --follow` | Tail logs |

### Deployment Commands

| Command | Description |
|---------|-------------|
| `muxi deploy` | Deploy to cloud (interactive) |
| `muxi deploy --target fly` | Deploy to Fly.io |
| `muxi deploy --target docker` | Generate Dockerfile |

---

## Secrets Management

### During Setup

```
? API Key: sk-ant-••••••••••••

Where should I store this?
  › .env file (gitignored, local only)
    Environment variable (export ANTHROPIC_API_KEY=...)
    System keychain
```

### .env File (Default)

```bash
# .env (auto-generated, gitignored)
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456789:ABC...
SLACK_BOT_TOKEN=xoxb-...
```

### formation.afs References

```yaml
llm:
  provider: anthropic
  api_key: ${{ env.ANTHROPIC_API_KEY }}

channels:
  telegram:
    enabled: true
    bot_token: ${{ env.TELEGRAM_BOT_TOKEN }}
```

### `muxi config secrets`

```
$ muxi config secrets

Secrets for: ./my-assistant/

  ANTHROPIC_API_KEY     ••••••••sk-ant-abc123    .env
  TELEGRAM_BOT_TOKEN    ••••••••789:ABCdef       .env
  SLACK_BOT_TOKEN       (not set)                -

? What would you like to do?
  › Add secret
    Update secret
    Remove secret
    Show secret value
```

---

## Diagnostics (`muxi doctor`)

```
$ muxi doctor

╭─────────────────────────────────────────╮
│           MUXI Diagnostics              │
╰─────────────────────────────────────────╯

Environment
  ✓ Python 3.11.5
  ✓ MUXI v0.1.0
  ✓ Formation found: ./my-assistant/

Configuration
  ✓ formation.afs valid
  ✓ LLM provider: anthropic
  ✓ API key present

Connections
  ✓ Anthropic API responding (model: claude-sonnet-4-20250514)
  ✓ Telegram bot online (@MyAssistantBot)
  ✗ Slack not configured

Proactive Check-ins
  ✓ Heartbeat enabled (every 30m)
  ✓ Active hours: 9am-6pm (user timezone)
  ✓ Weekends: quiet

Memory
  ✓ Vector DB connected
  ✓ 1,234 chunks stored
  ⚠ Knowledge graph not enabled

──────────────────────────────────────────

Issues found: 1 warning

  ⚠ Knowledge graph not enabled
    Run: muxi config memory --enable-graph
    Docs: https://docs.muxi.sh/memory/knowledge-graph

──────────────────────────────────────────

Overall: Healthy ✓
```

---

## Terminal Chat (`muxi chat`)

For quick testing without deploying:

```
$ muxi chat

╭─────────────────────────────────────────╮
│  my-assistant (local)                   │
│  Type /help for commands, /exit to quit │
╰─────────────────────────────────────────╯

You: What can you help me with?

Agent: I'm your personal productivity assistant. I can help with:
       • Managing tasks and reminders
       • Answering questions
       • Running scheduled jobs
       
       What's on your mind?

You: /status

Agent: Current status:
       • User: default (local testing)
       • Memory: 0 facts stored
       • Jobs: none scheduled
       • Uptime: 2m 34s

You: /exit

Session ended. Goodbye!
```

---

## Channel Setup Guides (Built into Wizard)

### Telegram

```
──────────────────────────────────────────
Telegram Setup

  1. Open Telegram and message @BotFather
  2. Send /newbot
  3. Choose a name (e.g., "My Assistant")
  4. Choose a username (must end in 'bot', e.g., "my_assistant_bot")
  5. Copy the token BotFather gives you

? Paste your bot token: 
```

### Slack

```
──────────────────────────────────────────
Slack Setup

  1. Go to api.slack.com/apps
  2. Click "Create New App" → "From scratch"
  3. Name it and select your workspace
  4. Go to "OAuth & Permissions"
  5. Add scopes: chat:write, users:read, im:history
  6. Install to workspace
  7. Copy the "Bot User OAuth Token" (starts with xoxb-)

? Paste your bot token: 

  8. Go to "Socket Mode" and enable it
  9. Generate an app-level token with connections:write
  
? Paste your app token (starts with xapp-):
```

### Discord

```
──────────────────────────────────────────
Discord Setup

  1. Go to discord.com/developers/applications
  2. Click "New Application"
  3. Go to "Bot" → "Add Bot"
  4. Copy the token
  5. Enable "Message Content Intent" under Privileged Intents
  6. Go to OAuth2 → URL Generator
  7. Select: bot, applications.commands
  8. Select permissions: Send Messages, Read Message History
  9. Copy the URL and open it to invite bot to your server

? Paste your bot token:
```

### Email

```
──────────────────────────────────────────
Email Setup (SMTP)

? SMTP Provider:
  › Gmail
    SendGrid
    AWS SES
    Custom SMTP

[If Gmail]
  1. Go to myaccount.google.com/apppasswords
  2. Generate an app password for "Mail"
  
? Gmail address: assistant@gmail.com
? App password: ••••••••••••••••

[If Custom]
? SMTP Host: smtp.example.com
? SMTP Port: 587
? Username: 
? Password:
? From address: assistant@example.com
```

---

## Implementation Priority

### Phase 1: Core Setup (Week 1)
- `muxi setup` wizard (fresh install flow)
- Formation creation
- LLM configuration + validation
- `.env` generation

### Phase 2: Channels (Week 2)
- Telegram setup flow
- Slack setup flow
- Discord setup flow
- Email setup flow

### Phase 3: Management (Week 3)
- `muxi setup` for existing installs
- `muxi config` commands
- `muxi doctor` diagnostics

### Phase 4: Polish (Week 4)
- `muxi chat` terminal interface
- Error handling and recovery
- Documentation integration

---

## Success Criteria

- Time from `pip install` to working agent: < 5 minutes
- Zero manual file editing required for basic setup
- All secrets validated before saving
- Clear error messages with fix suggestions
- `muxi doctor` catches 90% of common issues

---

## Open Questions

1. **Templates:** Should we offer starter templates (personal assistant, support bot, etc.)?
2. **Cloud secrets:** Support for AWS Secrets Manager, Vault, etc.?
3. **Team setup:** Multi-developer workflows (shared formations)?
4. **Upgrade path:** How to handle breaking changes in formation schema?

---

*End of Document*