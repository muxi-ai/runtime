# MUXI Runtime Production Readiness Plan

This document outlines the remaining features to implement and final tasks required to achieve production readiness for MUXI Runtime.

## 📋 Implementation Roadmap

### Phase 1: Complete Testing Coverage (Areas 9-13)
*Timeline: 1-2 weeks*

#### ✅ Test Plan Updated
The Comprehensive Test Plan has been reorganized with correct focus areas:

| Area | Focus | Status | Priority |
|------|-------|--------|----------|
| **Area 9** | Async Operations & Webhooks | 🔄 Ready | HIGH |
| **Area 10** | Streaming Responses | 🔄 Ready | HIGH |
| **Area 11** | Response Format & UI Elements | 🔄 Ready | MEDIUM |
| **Area 12** | Thinking Visibility | 🔄 Ready | LOW |
| **Area 13** | Scheduler & Jobs | 🔄 Ready | MEDIUM |

#### Implementation Order:
1. **Async & Webhooks** - Critical for long-running operations
2. **Streaming** - Essential for real-time responses
3. **Scheduler** - Important for automation
4. **Response Format** - Enhances user experience
5. **Thinking Visibility** - Nice-to-have transparency feature

---

### Phase 2: Large File Multimodal Processing
*Timeline: 2 weeks*

#### Overview
**GitHub Issue:** To be created
**Priority:** HIGH
**Description:** Add support for processing large audio/video files beyond current provider limits

**Problem Solved:**
- OpenAI has 25MB limit for audio files (Whisper API)
- Video files over 100MB often timeout
- No unified chunking strategy across providers
- Limited fallback mechanisms for oversized content

**Implementation Plan:**

**Week 1: Core Infrastructure**
```python
# File routing based on size and provider
class MultimodalFileRouter:
    def route_file(self, file_info, provider, content_type):
        if size < provider_limit:
            return DirectProcessing(provider)
        elif size < 2_000_000_000:  # 2GB
            return ChunkedProcessing(content_type, provider)
        else:
            return StreamingProcessing(content_type, provider)
```

**Week 2: Audio & Video Chunking**
- Audio chunking with overlap for continuity
- Video keyframe extraction and sampling
- Provider-specific optimizations
- Cross-provider fallback support

**Files to Create:**
- `src/muxi/services/multimodal/file_router.py`
- `src/muxi/services/multimodal/chunking/audio_chunker.py`
- `src/muxi/services/multimodal/chunking/video_chunker.py`
- `src/muxi/services/multimodal/chunking/result_fusion.py`

**Files to Modify:**
- `src/muxi/formation/overlord/overlord.py` - Update audio/video processing
- `src/muxi/services/multimodal/service.py` - Add chunking integration

**Success Metrics:**
- Process 500MB+ audio files successfully
- Process 1GB+ video files without timeout
- Maintain transcription accuracy >95%
- Provider fallback working seamlessly

**References:**
- [Full Implementation Plan](context/prds/large-file-multimodal-implementation-plan.md)

---

### Phase 3: New Features Implementation
*Timeline: 2-3 weeks*

#### 1. User Identity Resolution (Multiple IDs → Single User)
**GitHub Issue:** #52
**Priority:** HIGH
**Description:** Allow multiple external identifiers (email, Slack ID, Telegram ID) to resolve to a single user

**Problem Solved:**
- Users interact through multiple channels (Slack, Email, Telegram, Discord)
- Same user should maintain context/memory across all channels
- Prevents duplicate user records and fragmented memory

**Implementation Plan:**

**Step 1: Database Migration**
```sql
-- Create user_identifiers table
CREATE TABLE user_identifiers (
    id SERIAL PRIMARY KEY,
    identifier VARCHAR(255) NOT NULL,      -- email, slack_id, telegram_id, etc.
    identifier_type VARCHAR(50),           -- optional: 'email', 'slack', 'telegram'
    formation_id UUID NOT NULL,
    user_id UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(identifier, formation_id)
);

-- Index for fast lookups
CREATE INDEX idx_user_identifiers_lookup
ON user_identifiers(identifier, formation_id);
```

**Step 2: Update User Resolution Logic**
```python
# Updated user lookup in persistent memory
async def get_or_create_user(external_id: str, formation_id: str):
    # First check user_identifiers table
    user = await db.query("""
        SELECT u.* FROM users u
        JOIN user_identifiers ui ON u.id = ui.user_id
        WHERE ui.identifier = ? AND ui.formation_id = ?
    """, external_id, formation_id)

    if user:
        return user

    # Fall back to original users table check
    user = await db.query("""
        SELECT * FROM users
        WHERE external_user_id = ? AND formation_id = ?
    """, external_id, formation_id)

    if user:
        return user

    # Create new user if not found
    return await create_user(external_id, formation_id)
```

**Step 3: Association API**
```python
# API to associate multiple identifiers to same user
async def associate_user_identifier(
    main_external_id: str,
    additional_identifiers: List[Dict[str, str]],
    formation_id: str
):
    """
    Associates additional identifiers to an existing user.

    Args:
        main_external_id: Primary identifier of the user
        additional_identifiers: List of dicts with 'id' and optional 'type'
            [{"id": "user@email.com", "type": "email"},
             {"id": "U123456", "type": "slack"}]
        formation_id: Formation ID
    """
    # Get main user
    main_user = await get_user(main_external_id, formation_id)
    if not main_user:
        raise ValueError(f"User {main_external_id} not found")

    # Add all additional identifiers
    for identifier_info in additional_identifiers:
        await db.insert("user_identifiers", {
            "identifier": identifier_info["id"],
            "identifier_type": identifier_info.get("type"),
            "formation_id": formation_id,
            "user_id": main_user.id
        })
```

**Developer Usage:**
```python
# In developer's integration code
# When user verifies their email in Slack
await associate_user_identifier(
    slack_user_id,
    [{"id": user_email, "type": "email"}],
    formation_id
)

# When connecting multiple channels
await associate_user_identifier(
    primary_user_id,
    [
        {"id": "user@example.com", "type": "email"},
        {"id": "U12345", "type": "slack"},
        {"id": "@username", "type": "telegram"}
    ],
    formation_id
)
```

**Files to Modify:**
- `migrations/` - Add new migration for user_identifiers table
- `src/muxi/memory/persistent.py` - Update get_or_create_user logic
- `src/muxi/api/routes/users.py` - Add association endpoint
- `src/muxi/cli/commands/users.py` - Add CLI command for association

---

#### 2. Secrets Example File Generation
**GitHub Issue:** #18
**Priority:** HIGH
**Description:** Automatically generate example secrets files with proper structure

**Implementation Plan:**
```python
# When loading formation, if secrets.enc doesn't exist:
# 1. Detect all secret references in formation (${{ secrets.* }})
# 2. Generate secrets.example.yaml with structure:
secrets:
  OPENAI_API_KEY: "sk-..."  # OpenAI API key
  ANTHROPIC_API_KEY: "sk-ant-..."  # Anthropic API key
  DATABASE_URL: "postgresql://..."  # Database connection
  FAISSX_TENANT_ID: "..."  # FAISSx tenant ID
```

**Files to Modify:**
- `src/muxi/formation/formation.py` - Add example generation logic
- `src/muxi/formation/secrets.py` - Extract secret references
- `src/muxi/cli/commands/init.py` - Add CLI command

---

### Phase 4: System Improvements
*Timeline: 1-2 weeks*

#### 1. Security Hardening (Integrated Approach)
**Priority:** HIGH
**Description:** Enterprise-grade security through integrated routing

**Implementation:**
- Integrate security validation into existing agent routing prompt
- Add pattern pre-filter for instant blocking of obvious attacks (1ms)
- Leverage existing ObservabilityManager for response redaction
- Single LLM call for both routing AND security (50% cost reduction)

**Key Benefits:**
- **Zero additional infrastructure** - Uses existing agent_router.py
- **50% latency reduction** - Single LLM call instead of two
- **No new dependencies** - Removes need for separate security modules
- **Backward compatible** - Works with existing formations

**Files to Modify:**
- `src/muxi/formation/overlord/agent_router.py` - Enhanced routing prompt with security
- `src/muxi/formation/overlord/overlord.py` - Handle security blocks

**References:**
- [Full Security Hardening Strategy](context/prds/security-hardening-strategy.md)

---

#### 2. External Service Resilience
**Priority:** HIGH
**Description:** Escalating circuit breakers for external services that can be down for extended periods

**Implementation:**
- Escalating TTL lockouts (5min → 1hr → 24hr → permanent) for failing external services
- Service-type level configuration (LLM, MCP, A2A, Observability)
- OneLLM callback integration for fallback tracking
- Opt-in model with per-service configuration

**Key Benefits:**
- **80% reduction** in wasted API calls to down services
- **50% cost savings** during provider outages
- **Automatic recovery** when services become available
- **No cascading failures** from external service issues

**Files to Create:**
- `src/muxi/services/resilience/escalating_circuit_breaker.py`
- `src/muxi/services/resilience/external_service_resilience.py`

**References:**
- [Full External Service Resilience Strategy](context/prds/external-service-resilience.md)

---

#### 3. Observability Overhaul
**Goals:**
- Replace all `print()` statements with proper observability
- Reduce verbosity (currently too noisy)
- Linux boot-style initialization display

**Implementation:**
```python
# Current (verbose):
print(f"Loading agent {agent_id}...")
print(f"Agent {agent_id} initialized with model {model}")
print(f"Agent {agent_id} loaded {len(tools)} tools")

# New (concise):
observer.info("agent.load", agent_id=agent_id)  # Single event
```

**Boot-style display:**
```text
   __  _____  ___  ______  ___            __  _
  /  |/  / / / / |/_/  _/ / _ \__ _____  / /_(_)_ _  ___
 / /|_/ / /_/ />  <_/ /  / , _/ // / _ \/ __/ /  ' \/ -_)
/_/  /_/\____/_/|_/___/ /_/|_|\_,_/_//_/\__/_/_/_/_/\__/

Version: 1.3.0 | (c) 2025 Muxi, Inc.

[  OK  ] Started Formation Engine
[  OK  ] Loading formation <my-formation>
[  OK  ] Loaded 3 agents
[  OK  ] Connected to MCP servers (4 tools)
[  OK  ] Memory systems initialized
[  OK  ] MUXI Runtime ready (2.3s)
```

**Files to Modify:**
- `src/muxi/utils/observability.py` - Enhance observer
- `src/muxi/formation/formation.py` - Boot-style display
- All files with `print()` statements - Convert to observer

---

#### 2. Caching System
**GitHub Issue:** #56
**Priority:** MEDIUM
**Description:** Intelligent caching for improved performance

**Cache Layers:**
1. **LLM Response Cache** - Cache frequent queries
2. **Embedding Cache** - Cache computed embeddings
3. **MCP Tool Cache** - Cache tool discovery
4. **Knowledge Cache** - Already implemented ✅

**Implementation:**
```python
# LRU cache with TTL
@cache(ttl=3600, max_size=1000)
async def process_query(query: str, context: dict):
    # Expensive LLM call
    return await llm.generate(query, context)
```

**Files to Create:**
- `src/muxi/cache/manager.py` - Cache manager
- `src/muxi/cache/backends/redis.py` - Redis backend
- `src/muxi/cache/backends/memory.py` - In-memory backend

---

### Phase 5: API Implementation
*Timeline: 1-2 weeks*

#### Formation API
**PRDs:**
- `context/prds/formation-api.md`
- `context/prds/formation-api-implementation-plan.md`

**Current Status:**
- OpenAPI schema defined ✅
- AVChat endpoint added ✅
- Core endpoints need implementation

**Priority Endpoints:**
1. `/health` - Health check
2. `/chat` - Main chat endpoint ✅ (partial)
3. `/avchat` - Audio/video chat ✅ (schema only)
4. `/operations/{id}` - Async operation status
5. `/formations` - Formation management

**Implementation Files:**
- `src/muxi/api/server.py` - FastAPI server
- `src/muxi/api/routes/chat.py` - Chat endpoints
- `src/muxi/api/routes/operations.py` - Async operations
- `src/muxi/api/routes/admin.py` - Admin endpoints

---

#### Webhook Triggers (Part of API)
**GitHub Issue:** #48
**Priority:** HIGH
**Description:** Simple webhook → trigger template → overlord.chat pipeline

The goal is to create a webhook-like interface that will trigger request.

**How It Works:**
1. Webhook receives POST to `/trigger` with payload
2. Load template from `formations/triggers/{trigger_name}.md`
3. Render template using existing formation template system (`${{ data.* }}`)
4. Call `overlord.chat()` with rendered message + `use_async=True`

**Payload Structure:**
```json
{
  "user_id": "ran@aroussi.com",  // Optional, defaults to "0"
  "trigger": "new-github-issue",   // Required trigger name
  "data": {                        // Data to inject into template
    "issue_id": 712,
    "repository": "muxi-ai/runtime"
  }
}
```

**Implementation (in API layer):**
```python
# src/muxi/api/routes/triggers.py
@router.post("/trigger")
async def handle_trigger(request: Request):
    payload = await request.json()

    # Extract fields
    user_id = payload.get("user_id", "0")  # Default like overlord.chat
    trigger_name = payload.get("trigger")
    data = payload.get("data", {})

    if not trigger_name:
        raise HTTPException(400, "trigger field required")

    # Load trigger template
    trigger_path = Path(f"formations/triggers/{trigger_name}.md")
    if not trigger_path.exists():
        raise HTTPException(404, f"Trigger '{trigger_name}' not found")

    template_content = trigger_path.read_text()

    # Use existing formation template parser (not Jinja2!)
    # Same system that handles ${{ secrets.* }}
    message = render_template(template_content, {"data": data})

    # Send to runtime
    response = await overlord.chat(
        message=message,
        user_id=user_id,
        use_async=True
    )
    return {"status": "triggered", "request_id": response["request_id"]}
```

**Example Trigger Template:**
```markdown
# formations/triggers/new-github-issue.md
---
trigger: new-github-issue
---

Please review issue #${{ data.issue_id }} on GitHub repository ${{ data.repository }} using the GitHub agent and provide a summary of the issue, suggest a solution, and draft a response.
```

**Files to Create:**
- `src/muxi/api/routes/triggers.py` - Webhook endpoint handler
- `formations/triggers/` - Directory for trigger templates
- Documentation for trigger template syntax

**Usage Examples:**
```bash
# GitHub issue trigger
POST https://api.formation.ltd/trigger
{
  "user_id": "ran@aroussi.com",
  "trigger": "new-github-issue",
  "data": {
    "issue_id": 712,
    "repository": "muxi-ai/runtime"
  }
}
# → "Please review issue #712 on GitHub repository muxi-ai/runtime..."

# Linear ticket trigger (user_id optional)
POST https://api.formation.ltd/trigger
{
  "trigger": "linear-ticket",
  "data": {
    "team_id": "TEAM-123",
    "ticket_id": "ENG-456",
    "title": "API performance regression"
  }
}
# → Uses user_id="0" by default
```

---

### Phase 6: Final Polish
*Timeline: 1 week*

#### 1. Code Cleanup
- Add comprehensive docstrings
- Remove dead code
- Consistent naming conventions
- Type hints everywhere

#### 2. Documentation
- API documentation
- Deployment guide
- Performance tuning guide
- Security best practices

#### 3. Performance Optimization
- Profile hot paths
- Optimize database queries
- Reduce memory footprint
- Improve startup time

---

## 📊 Success Metrics

### Performance Targets
- **Startup Time:** < 3 seconds
- **Simple Query:** < 2 seconds
- **Complex Query:** < 30 seconds
- **Memory Usage:** < 500MB baseline
- **Concurrent Users:** 100+

### Quality Metrics
- **Test Coverage:** > 80%
- **Code Quality:** Flake8 + Pyright passing
- **Documentation:** All public APIs documented
- **Error Handling:** No unhandled exceptions

---

## 🚀 Launch Readiness Checklist

### Must Have (P0)
- [ ] Areas 9-10 tests complete (Async, Streaming)
- [ ] Large file multimodal processing - Handle 500MB+ audio/1GB+ video
- [ ] User identity resolution (#52) - Multiple IDs → Single User
- [ ] Secrets example generation (#18)
- [ ] API implementation (core endpoints + webhook triggers #48)
- [ ] Observability overhaul
- [ ] Production deployment guide

### Should Have (P1)
- [ ] Area 11 tests (Response Format)
- [ ] Area 13 tests (Scheduler)
- [ ] Caching system (#56)
- [ ] Performance optimization

### Nice to Have (P2)
- [ ] Area 12 tests (Thinking Visibility)
- [ ] Linux boot-style display
- [ ] Advanced API endpoints
- [ ] Comprehensive metrics dashboard

---

## 📅 Timeline Summary

**Total Duration:** 7-9 weeks

1. **Weeks 1-2:** Complete test coverage (Areas 9-13)
2. **Weeks 3-4:** Large file multimodal processing
3. **Weeks 5-6:** Implement new features (identity, secrets, triggers)
4. **Week 7:** System improvements (Observability, Caching)
5. **Week 8:** API implementation
6. **Week 9:** Final polish and documentation

**Target Production Date:** End of current quarter

---

## 🎯 Definition of Done

The MUXI Runtime will be considered production-ready when:

1. ✅ All P0 items complete
2. ✅ Performance targets met
3. ✅ 80% test coverage achieved
4. ✅ Zero critical bugs
5. ✅ Documentation complete
6. ✅ Deployment validated in production environment
7. ✅ Security review passed
8. ✅ Load testing passed (100+ concurrent users)

---

## 📝 Notes

- Focus on stability over new features
- Prioritize user-facing improvements
- Maintain backward compatibility
- Document all breaking changes
- Communicate progress weekly

**Last Updated:** 2025-09-04
