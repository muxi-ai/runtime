# Initialization Events & Fail-Fast Architecture Proposal

## Problem Statement

Critical startup resources (SOPs, knowledge sources, secrets) are currently treated as **runtime observability events** instead of **initialization events**, violating the fail-fast principle.

### Current Issues

#### 1. **SOPs - Silent Failures**
```python
# src/muxi/formation/workflow/sops.py lines 84-96
try:
    observability.observe(
        event_type=observability.ConversationEvents.SOP_LOADED,  # ❌ Wrong event type!
        level=observability.EventLevel.INFO,
        data={"sop_count": len(self.sops), ...},
        description=f"Loaded {len(self.sops)} SOPs from {self.sop_dir}"
    )
except Exception:
    pass  # ❌ SILENTLY IGNORES ALL ERRORS!
```

**Problems:**
- Uses `ConversationEvents.SOP_LOADED` (runtime event) not init event
- Wrapped in try/except with `pass` - completely silent failure
- Errors during initialization are invisible
- No `InitEventFormatter` output - developer never sees it during startup
- No fail-fast - misconfigured SOPs won't stop formation

#### 2. **Knowledge Sources - Log and Continue**
```python
# src/muxi/formation/agents/knowledge/handler.py lines 474-480
except Exception as e:
    observability.observe(
        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,  # ❌ Wrong event type!
        level=observability.EventLevel.ERROR,
        data={"source_path": source_path, "error": str(e)},
        description="Failed to add knowledge source"
    )
    # ❌ No raise - continues silently!
    # ❌ No InitEventFormatter - invisible during startup
```

**Problems:**
- Uses `SystemEvents.KNOWLEDGE_SOURCE_FAILED` (runtime event)
- Logs error but doesn't raise - continues with missing knowledge
- No InitEventFormatter output during startup
- Developer never knows knowledge is broken until runtime

#### 3. **Multiple KNOWLEDGE_SOURCE_LOADED Events**
```python
# Knowledge sources emit 20+ observability events throughout loading
# Lines 322, 348, 357, 445, 756, 785, 874, 923, 938, 951, 1027, 1059, 1068, 1096, 1147, 1170, 1193, 1223...

# All using SystemEvents.KNOWLEDGE_SOURCE_LOADED
# None using InitEventFormatter
# All buried in observability logs during startup
```

**Problems:**
- Chatty runtime events during initialization
- No clear "✓ Knowledge loaded: 3 sources" during startup
- Can't see at a glance if knowledge loading succeeded

### What Developers See Now

**Current startup output (SOPs fail silently):**
```
══════════════════════════════════════════════════════════════════
                       Initializing Formation
══════════════════════════════════════════════════════════════════
  ✓ Working memory (remote mode)
  ✓ Initializing buffer memory: hybrid, 100 messages, contextual search enabled
  ✓ Initializing persistent memory: Memobase / multi-user mode
  ✓ Database schema ready: 15 tables initialized
  ✓ Loaded agent 'research-assistant': role: research
  ✓ Loaded agent 'code-expert': role: coding
  
  ✓ Formation initialized successfully in 2.3s
══════════════════════════════════════════════════════════════════
```

**Problem:** No mention of SOPs, knowledge sources, or if they failed!

## Proposed Solution

### Linux Init-Style Fail-Fast Architecture

Resources should be categorized and handled appropriately:

#### **CRITICAL Resources** (must fail fast):
- Secrets (API keys, credentials)
- Formation configuration schema
- Required knowledge sources (if explicitly required)
- Database connection for persistent memory

#### **IMPORTANT Resources** (show in init, warn if fail, continue):
- SOPs (if present)
- Optional knowledge sources
- MCP servers (already doing this correctly!)
- A2A registries (already doing this correctly!)

#### **OPTIONAL Resources** (silent OK):
- Cached embeddings
- Optional services

### Recommended Changes

#### 1. **SOPs Should Use InitEventFormatter**

**BEFORE:**
```python
# sops.py lines 84-96
try:
    observability.observe(
        event_type=observability.ConversationEvents.SOP_LOADED,
        level=observability.EventLevel.INFO,
        data={"sop_count": len(self.sops)},
        description=f"Loaded {len(self.sops)} SOPs"
    )
except Exception:
    pass
```

**AFTER:**
```python
# sops.py during __init__
if self.sop_dir and self.sop_dir.exists():
    try:
        self._scan_directory()
        if self.sops:
            self.enabled = True
            self._hydrate_from_cache()
            
            # Init event - visible during startup
            from ...datatypes.observability import InitEventFormatter
            sop_names = ", ".join(list(self.sops.keys())[:3])
            if len(self.sops) > 3:
                sop_names += f" +{len(self.sops) - 3} more"
            print(InitEventFormatter.format_ok(
                f"SOPs loaded: {len(self.sops)} procedures",
                sop_names
            ))
    except Exception as e:
        # Fail fast with clear error
        from ...datatypes.observability import InitEventFormatter
        print(InitEventFormatter.format_fail(
            f"Failed to load SOPs from {self.sop_dir}",
            str(e)
        ))
        raise RuntimeError(f"SOP initialization failed: {e}") from e
```

#### 2. **Knowledge Sources Should Use InitEventFormatter**

**BEFORE:**
```python
# Multiple observability.observe() calls scattered throughout
observability.observe(
    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
    level=observability.EventLevel.INFO,
    description="Knowledge loading completed",
    data={"summary": {...}}
)
```

**AFTER:**
```python
# knowledge/handler.py after loading all sources
from ...datatypes.observability import InitEventFormatter

# Summary at end of load_from_config()
if processed_count > 0 or skipped_count > 0:
    total = processed_count + skipped_count
    details = f"{processed_count} processed, {skipped_count} cached"
    if cleanup_count > 0:
        details += f", {cleanup_count} removed"
    
    print(InitEventFormatter.format_ok(
        f"Knowledge sources: {total} loaded",
        details
    ))
elif knowledge_sources:
    # Had sources but all failed
    print(InitEventFormatter.format_fail(
        "Failed to load any knowledge sources",
        f"{len(knowledge_sources)} sources configured but failed"
    ))
    # Decide: fail fast or continue?
    raise RuntimeError("Knowledge source initialization failed")
```

#### 3. **Distinguish Critical vs Optional**

**Formation YAML should specify:**
```yaml
agents:
  - id: research-agent
    knowledge:
      sources:
        - path: ./docs/critical-info.md
          required: true  # ← Fail fast if missing!
        - path: ./docs/optional-guide.md
          required: false  # ← Warn but continue
```

**Implementation:**
```python
# In knowledge/handler.py
for source_config in knowledge_sources:
    try:
        # Load source...
    except Exception as e:
        if source_config.get('required', False):
            # FAIL FAST for critical resources
            print(InitEventFormatter.format_fail(
                f"Required knowledge source failed: {source_path}",
                str(e)
            ))
            raise RuntimeError(f"Critical knowledge source failed: {source_path}") from e
        else:
            # WARN but continue for optional resources  
            print(InitEventFormatter.format_warn(
                f"Optional knowledge source skipped: {source_path}",
                str(e)
            ))
            continue
```

### Proposed Startup Output

**WITH proper init events (fail-fast example):**
```
══════════════════════════════════════════════════════════════════
                       Initializing Formation
══════════════════════════════════════════════════════════════════
  ✓ Working memory (remote mode)
  ✓ Initializing buffer memory: hybrid, 100 messages, contextual search enabled
  ✓ Initializing persistent memory: Memobase / multi-user mode
  ✓ Database schema ready: 15 tables initialized
  
  ✓ SOPs loaded: 3 procedures: user-onboarding, bug-triage, release-process
  
  ✓ Knowledge sources: 5 loaded: 4 processed, 1 cached
  
  ✓ Loaded agent 'research-assistant': role: research
  ✓ Loaded agent 'code-expert': role: coding
  
  ✓ Formation initialized successfully in 2.3s
══════════════════════════════════════════════════════════════════
```

**WITH failure (fail-fast example):**
```
══════════════════════════════════════════════════════════════════
                       Initializing Formation
══════════════════════════════════════════════════════════════════
  ✓ Working memory (remote mode)
  ✓ Initializing buffer memory: hybrid, 100 messages
  ✓ Database schema ready: 15 tables initialized
  
  ✗ Failed to load SOPs from ./sops
    FileNotFoundError: [Errno 2] No such file or directory: './sops/user-onboarding.md'
══════════════════════════════════════════════════════════════════

Formation initialization failed. Please fix the errors above.
```

## Benefits

1. **Developer Experience** - Errors visible immediately during `muxi start`
2. **Fail Fast** - Catch misconfigurations before deployment
3. **Clear Visibility** - See exactly what loaded during startup
4. **Linux Init Pattern** - Familiar model for operations teams
5. **Reduced Debugging Time** - No hunting through observability logs for init failures
6. **Production Safety** - Prevents running with missing critical resources

## Implementation Priority

### Phase 1 (High Priority):
1. ✅ MCP servers - Already correct! (uses InitEventFormatter + fail-fast)
2. ✅ Secrets - Already correct! (proper error handling)
3. 🔴 **SOPs** - Add InitEventFormatter + fail-fast
4. 🔴 **Knowledge sources** - Add InitEventFormatter + required/optional distinction

### Phase 2 (Medium Priority):
5. Document loading during agent init
6. Credential resolution during startup

### Phase 3 (Nice to Have):
7. Add `required: true/false` to all startup resources in schema
8. Unified init event system for all resources

## Files Requiring Changes

1. **src/muxi/formation/workflow/sops.py** - Lines 84-96
2. **src/muxi/formation/agents/knowledge/handler.py** - Multiple locations
3. **src/muxi/formation/agents/knowledge/base.py** - Error handling
4. **schemas/formation/formation.yaml** - Add `required` field to knowledge sources

## Open Questions

1. **Should SOPs be required or optional by default?**
   - Recommendation: Optional (warn but continue if missing)
   
2. **Should knowledge sources be required by default?**
   - Recommendation: Optional unless explicitly marked `required: true`
   
3. **Should we remove all the chatty runtime observability events during init?**
   - Recommendation: Yes - replace with ONE InitEventFormatter line per resource type
   
4. **Should missing SOP directory be an error or just disabled?**
   - Recommendation: Silent disable (current behavior OK), but if directory exists but files fail to parse, that should be an error

## Backward Compatibility

All changes are backward compatible:
- New `required` field defaults to `false` 
- Existing formations continue working
- Only adds visibility, doesn't change behavior for valid configs
- Only fails fast on genuinely broken configurations
