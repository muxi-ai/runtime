# User Synopsis System

## Overview

The User Synopsis system provides LLM-synthesized, cached summaries of user context for injection into enhanced messages. It uses a sophisticated two-tier caching architecture to balance freshness with performance.

## Configuration

User synopsis can be configured in your formation YAML:

```yaml
memory:
  persistent:
    user_synopsis:
      enabled: true      # Enable/disable synopsis feature (default: true)
      cache_ttl: 3600    # Cache TTL in seconds (default: 3600 = 1 hour)
```

**Parameters:**

- **`enabled`** (boolean, default: `true`)
  - Enable or disable user synopsis generation
  - When disabled, no synopsis is generated or cached
  - Use case: Disable to save LLM costs if not needed

- **`cache_ttl`** (integer, default: `3600`)
  - Time-to-live for synopsis caches in seconds
  - Applies to: Context synopsis (preferences/activities) and empty identity cache
  - Range: 60 - 86400 (1 minute to 24 hours)
  - Lower values: More fresh data, higher LLM costs
  - Higher values: Less fresh data, lower LLM costs

**Note:** Identity synopsis with actual data uses permanent cache regardless of `cache_ttl`. The TTL only applies to the context synopsis and empty identity cache entries.

## Architecture

### Two-Tier Synopsis Design

The system splits user information into two categories with different update frequencies and caching strategies:

```
┌──────────────────────────────────────────────────────┐
│                    User Synopsis                     │
│                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │  Identity Synopsis   │  │  Context Synopsis    │  │
│  │  (Tier 1)            │  │  (Tier 2)            │  │
│  ├──────────────────────┤  ├──────────────────────┤  │
│  │ Collections:         │  │ Collections:         │  │
│  │ - user_identity      │  │ - preferences        │  │
│  │ - relationships      │  │ - activities         │  │
│  │ - work_projects      │  │                      │  │
│  ├──────────────────────┤  ├──────────────────────┤  │
│  │ Cache: Permanent     │  │ Cache: 1-hour TTL    │  │
│  │ Invalidation:        │  │ Invalidation:        │  │
│  │  Explicit on update  │  │  Automatic (TTL)     │  │
│  └──────────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Tier 1: Identity Synopsis

**Purpose:** Stable user information that rarely changes

**Collections:**
- `user_identity` - Name, role, occupation
- `relationships` - Team members, colleagues, contacts
- `work_projects` - Current work, projects, initiatives

**Caching Strategy:**
- **TTL:** None (permanent cache)
- **Invalidation:** Explicit - triggered when identity collections are updated
- **Namespace:** `user_synopsis_identity`

**Rationale:** Identity information changes infrequently (job changes, team moves). When it does change, it's critical to update immediately. Permanent caching minimizes LLM costs while explicit invalidation ensures accuracy.

**Example Output:**
```
Ran Aroussi is the Founder of MUXI AI, working closely with the engineering
team on the runtime platform.
```

### Tier 2: Context Synopsis

**Purpose:** Dynamic user information that changes frequently

**Collections:**
- `preferences` - Communication style, likes/dislikes, opinions
- `activities` - Current interests, hobbies, routines

**Caching Strategy:**
- **TTL:** Configurable (default: 3600 seconds / 1 hour)
- **Invalidation:** Automatic via TTL expiration
- **Namespace:** `user_synopsis_context`

**Rationale:** Preferences and activities evolve naturally over time. A configurable cache TTL allows tuning freshness vs. cost based on your use case.

**Example Output:**
```
He prefers concise, technical communication and is currently focused on
implementing the user synopsis feature.
```

## Cache Invalidation

### Identity Synopsis Invalidation

Identity synopsis cache is invalidated in these scenarios:

1. **Automatic Extraction Updates** (Primary Path)
   - When extraction system adds memories to identity collections
   - Triggered in `extractor.py:_process_extraction_results()`
   - Only fires for `user_identity`, `relationships`, `work_projects` updates

2. **Manual API Updates** (Legacy/Developer Path)
   - When `add_user_context()` or `clear_user_context()` called
   - Invalidates BOTH identity and context caches (safe default)

### Context Synopsis Invalidation

Context synopsis uses TTL-based invalidation:
- Cache expires after 1 hour automatically
- No manual invalidation needed
- Next access triggers fresh LLM synthesis

### Cache Keys

Both tiers use `users.id` (internal integer database ID) as cache keys, not `external_user_id`:

```python
# Cache key pattern
cache_key = user_id  # e.g., 42 (integer from users.id)
namespace = "user_synopsis_identity" | "user_synopsis_context"
```

**Why integers?**
- More efficient than string keys (smaller memory footprint)
- Consistent with how internal memory operations work
- Direct database lookups without string manipulation
- Simpler and faster cache operations

**Lookup flow:**
```
external_user_id="john@company.com"
    ↓
long_term_memory.get_user_id(external_user_id)
    ↓
users.id=42 (integer)
    ↓
Cache key: 42
```

## LLM Synthesis

### Prompt Engineering

Each tier uses optimized prompts tailored to its purpose:

**Identity Synopsis Prompt:**
```
You are analyzing user identity information. Below are facts about a user:

[memories]

Synthesize these facts into 1-2 natural sentences about who they are. Focus ONLY on:
- Name, role, occupation
- Team/relationships
- Work projects

Write in third person. Be concise and factual.
```

**Context Synopsis Prompt:**
```
You are analyzing user preferences and activities. Below are facts about a user:

[memories]

Synthesize these facts into 1-2 natural sentences about their current context. Focus ONLY on:
- Communication preferences and style
- Current activities and interests
- Recent focus areas

Write in third person. Be concise and factual. Use present tense.
```

### LLM Configuration

- **Model:** `overlord.extraction_model` (typically `gpt-4o-mini`)
- **Temperature:** 0.3 (consistent but slightly creative)
- **Max Tokens:** 100 (concise output)
- **Graceful Degradation:** Returns empty string on failure

## Memory Sources

### Rich Collections vs Legacy context_memory

**Old Approach (Deprecated):**
- Queried `context_memory_{user_id}` collection
- Sparse, manually-populated data
- Most users had empty or minimal data

**New Approach (Current):**
- Queries 5 rich collections populated by automatic extraction
- Much more comprehensive user data
- Better coverage and accuracy

**Collections Queried:**
| Collection | Tier | Items Retrieved |
|------------|------|-----------------|
| `user_identity` | Identity | Top 3 |
| `relationships` | Identity | Top 3 |
| `work_projects` | Identity | Top 3 |
| `preferences` | Context | Top 3 |
| `activities` | Context | Top 3 |

**Note:** `conversations` and `default` collections are excluded to avoid noise.

## Performance Characteristics

### Cache Hit Rates

**Expected Performance:**

| Scenario | Identity Cache | Context Cache | LLM Calls |
|----------|----------------|---------------|-----------|
| New user, first message | Miss | Miss | 2 |
| Existing user, no updates | Hit | Hit | 0 |
| User mentions new preference | Hit | Hit/Miss* | 0-1 |
| User changes job | Miss (invalidated) | Hit | 1 |
| Hourly active user | Hit | Miss (TTL) | 1/hour |

*Depends on whether 1-hour TTL has expired

### Cost Analysis

**Assumptions:**
- User has 100 conversations/month
- Identity changes: 0.1x/month (once every 10 months)
- Preferences mentioned: 10x/month

**Old Approach (No Caching):**
- LLM calls: 100/month
- Cost: $X

**New Approach (Two-Tier):**
- Identity LLM calls: 0.1/month (only on changes)
- Context LLM calls: ~30/month (1/hour for active hours)
- Total: ~30/month
- **Savings: ~70%**

### Memory Usage

Each cached synopsis:
- Identity: ~100-150 characters
- Context: ~100-150 characters
- Total per user: ~250-300 bytes

For 1000 concurrent users: ~250-300 KB total memory

## FIFO Exclusion

Both synopsis namespaces are excluded from FIFO cleanup in `working.py`:

```python
_NAMESPACES_EXCLUDED_FROM_FIFO = [
    "knowledge",
    "sops",
    "user_synopsis_identity",  # Permanent cache, explicit invalidation
    "user_synopsis_context",   # TTL-based, self-managing
]
```

**Rationale:**
- Identity: We control lifecycle via explicit invalidation
- Context: TTL handles automatic cleanup
- Prevents premature eviction and unnecessary LLM regeneration

## Usage

### Automatic Integration

User synopsis is **automatically** injected into enhanced messages by `chat_orchestrator.py`:

```python
# In chat_orchestrator._enhance_message_with_context()

# Get user synopsis (cached)
user_profile_text = await self.overlord.get_user_synopsis(external_user_id=user_id)

# Inject into enhanced message
if user_profile_text:
    enhanced_parts.append("=== USER PROFILE ===")
    enhanced_parts.append(user_profile_text)
```

No developer action required - works automatically for all agents.

### Manual Access (Advanced)

For custom implementations:

```python
# Get combined synopsis
synopsis = await overlord.get_user_synopsis(external_user_id="user_123")

# Or access individual tiers (internal use)
identity = await overlord.user_context_manager._get_identity_synopsis("user_123")
context = await overlord.user_context_manager._get_context_synopsis("user_123")
```

### Manual Cache Invalidation (Advanced)

For edge cases requiring manual invalidation:

```python
# Invalidate identity synopsis cache
await overlord.user_context_manager.invalidate_identity_synopsis_cache("user_123")

# Note: Context synopsis uses TTL, no manual invalidation needed
```

## Error Handling

The system uses graceful degradation at every level:

1. **User Doesn't Exist:** Returns empty string
2. **No Collections Data:** Returns empty string, caches empty with TTL
3. **LLM Synthesis Fails:** Returns empty string
4. **Cache Write Fails:** Logs but continues (non-critical)
5. **Cache Invalidation Fails:** Logs but continues (non-critical)

**Result:** Enhanced messages work even if synopsis system fails.

## Monitoring

### Key Metrics to Track

1. **Cache Hit Rate:**
   - Identity synopsis: Expected >99%
   - Context synopsis: Expected ~90%

2. **LLM Synthesis Calls:**
   - Monitor rate and costs
   - Alert on unexpected spikes

3. **Cache Invalidation Events:**
   - Track identity invalidations (indicates user updates)
   - Should correlate with extraction activity

4. **Synthesis Quality:**
   - Sample and review generated synopses
   - Ensure coherence and accuracy

## Future Enhancements

### Potential Improvements

1. **Smart Context Refresh:**
   - Invalidate context cache when significant preference changes detected
   - Avoid waiting full 1-hour TTL for important updates

2. **Personalized Prompts:**
   - Tailor synthesis prompts based on user communication style
   - E.g., more formal for business users, casual for personal

3. **Multi-Modal Context:**
   - Include visual preferences, timezone, etc.
   - Richer user representation

4. **A/B Testing:**
   - Compare single-tier vs two-tier performance
   - Optimize TTL values based on real usage

5. **Context_memory Deprecation:**
   - Remove legacy `context_memory` collection entirely
   - Simplify codebase (see Issue #XX)

## Related Documentation

- **User Context API:** See `docs/memory/user-context.md`
- **Memory Architecture:** See `docs/memory/architecture.md`
- **LLM Service:** See `docs/services/llm.md`
- **Extraction System:** See `docs/memory/extraction.md`

## Troubleshooting

### Synopsis Not Appearing

**Symptom:** User synopsis not shown in enhanced messages

**Diagnosis:**
1. Check multi-user mode enabled: `overlord.is_multi_user == True`
2. Check user_id not "0" (anonymous user)
3. Check collections have data: Query `user_identity`, `preferences` collections
4. Check LLM model available: `overlord.extraction_model` exists

**Resolution:** Enable multi-user mode and ensure extraction is populating collections.

### Stale Synopsis Data

**Symptom:** Synopsis shows old information

**Diagnosis:**
1. Check cache invalidation: Did identity collection update trigger invalidation?
2. Check TTL expiry: Has 1-hour window passed for context synopsis?
3. Check extraction: Is extraction system running and updating collections?

**Resolution:**
- Manual invalidation: `await overlord.user_context_manager.invalidate_identity_synopsis_cache(user_id)`
- Wait for TTL: Context refreshes automatically within 1 hour
- Fix extraction: Ensure extraction system is active and working

### High LLM Costs

**Symptom:** Unexpected LLM synthesis costs

**Diagnosis:**
1. Check cache hit rates: Are caches being invalidated too frequently?
2. Check user activity: Many new users or high turnover?
3. Check extraction: Is extraction over-triggering on minor updates?

**Resolution:**
- Review invalidation logic in `extractor.py`
- Consider increasing context TTL (trade freshness for cost)
- Optimize extraction to reduce false positives

## Implementation Details

### Code Organization

```
src/muxi/formation/memory/user_context.py
├── get_user_synopsis()                  # Public API - returns combined synopsis
├── _get_identity_synopsis()             # Tier 1 - permanent cache
├── _get_context_synopsis()              # Tier 2 - 1hr TTL
├── _synthesize_synopsis_with_llm()      # LLM synthesis with type-specific prompts
├── invalidate_identity_synopsis_cache() # Manual invalidation helper
├── add_user_context()                   # Invalidates both caches
└── clear_user_context()                 # Invalidates both caches

src/muxi/services/memory/extractor.py
└── _process_extraction_results()        # Invalidates identity cache on updates

src/muxi/services/memory/working.py
└── _NAMESPACES_EXCLUDED_FROM_FIFO       # FIFO exclusions for both namespaces

src/muxi/formation/overlord/chat_orchestrator.py
└── _enhance_message_with_context()      # Injects synopsis into messages
```

### Testing

**Unit Tests:**
```bash
pytest tests/unit/test_user_synopsis.py
```

**Integration Tests:**
```bash
pytest tests/integration/test_synopsis_caching.py
pytest tests/integration/test_synopsis_invalidation.py
```

**E2E Tests:**
```bash
bash .claude/scripts/test-and-log.sh e2e/tests/test_user_synopsis.py
```

## Version History

- **v1.0 (Current):** Two-tier architecture with identity/context split
- **v0.1 (Deprecated):** Single-tier using context_memory collection

---

**Last Updated:** 2025-01-XX
**Author:** MUXI Runtime Team
**Status:** Production
