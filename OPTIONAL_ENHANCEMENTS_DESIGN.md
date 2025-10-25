# Optional Enhancements - Design Document

**Date:** October 25, 2025  
**Status:** Approved for Implementation  
**Effort:** ~17-21 hours total

---

## Overview

This document captures the design decisions for 6 optional production enhancements identified during code review. All enhancements follow the KISS (Keep It Simple, Stupid) principle and are backward-compatible.

---

## 1. Global Workflow Timeout

### Decision
**Single hard limit: 7200 seconds (2 hours)**

### Rationale
- Workflows can legitimately run for long periods (data processing, research)
- Single `max_timeout_seconds` parameter - no complexity of default vs max tiers
- Hard ceiling prevents runaway workflows
- 2 hours is reasonable for most workflows; can be adjusted if needed

### Configuration
```yaml
workflow:
  max_timeout_seconds: 7200  # Hard ceiling
```

### Implementation Location
- `src/muxi/formation/workflow/executor.py` - Add timeout wrapper
- Formation config loading

### Implementation Notes
- Use `asyncio.timeout()` to wrap entire workflow execution
- On timeout: Log error event with workflow details, fail with clear message
- No per-workflow override - single global limit

### Effort
~2 hours

---

## 2. Database Query Timeout

### Decision
**30 seconds statement timeout, apply to all queries**

### Rationale
- Prevents hung queries from exhausting connection pool
- 30 seconds is aggressive but reasonable
- "Until reality tells us otherwise" - can adjust if legitimate slow queries appear
- Standard PostgreSQL best practice

### Configuration
```yaml
database:
  statement_timeout_seconds: 30
```

### Implementation Location
- `src/muxi/services/db.py` - Update `create_engine()` calls
- Apply to both sync and async engines

### Implementation Notes
```python
# Sync engine
connect_args={
    "options": "-c statement_timeout=30000"  # milliseconds
}

# Async engine
connect_args={
    "server_settings": {
        "statement_timeout": "30000",
        "idle_in_transaction_session_timeout": "60000"
    }
}
```

### Effort
~1 hour

---

## 3. Credential Salt Configuration

### Decision
**Make salt configurable per formation, remove hardcoded value**

### Rationale
- Currently hardcoded: `SALT = b"muxi-user-credentials-salt-v1"` for everyone
- Different formations should be able to use different salts
- Salt travels with formation (portable)
- Devs manage their own salt values (not our responsibility)
- Backward compatible: Default to old hardcoded value if not specified

### Configuration
```yaml
credentials:
  encryption:
    key: ${CREDENTIAL_ENCRYPTION_KEY}
    salt: "formation-specific-salt-2025"  # Optional, defaults to v1 salt
```

### Implementation Location
- `src/muxi/formation/credentials/encrypted.py` - Remove hardcoded SALT
- Formation config loading - Pass salt to EncryptedCredentialsStore

### Implementation Notes
- Salt does not need to be secret (just unique)
- Can be stored in plain YAML (not secrets.env)
- Backward compatibility: `salt = config.get('credentials.encryption.salt', 'muxi-user-credentials-salt-v1')`

### Effort
~2 hours

---

## 4. Key Rotation Utility

### Decision
**Simple utility script - devs run manually when needed**

### Rationale
- No automated rotation system (over-engineering)
- Devs are responsible for:
  - Deciding when to rotate
  - Managing rotation schedule
  - Testing rotation in their environment
- We provide the tool, they own the process

### Configuration
**No YAML configuration** - This is a developer utility

### Implementation Location
- `scripts/rotate_credential_keys.py` - New utility script

### Implementation Notes
```bash
# Usage
python scripts/rotate_credential_keys.py \
  --formation-id myformation \
  --old-salt "old-salt-value" \
  --new-salt "new-salt-value"
```

**Features:**
- Accepts old/new salt as arguments
- Iterates all users in credentials table
- Decrypts with old salt → re-encrypts with new salt
- Transaction-based (rollback on error)
- Progress reporting
- Dry-run mode for testing

**Error Handling:**
- If decryption fails with old salt: Skip user, warn, continue
- If encryption fails with new salt: Abort entire rotation (rollback)

### Effort
~6-8 hours

---

## 5. Input Length Limits

### Decision
**Centralized `input_limits` section in formation YAML**

### Rationale
- All limits in one place (easy to find and modify)
- Formation-level configuration
- Prevents DoS attacks from oversized inputs
- Better error messages than generic timeouts

### Configuration
```yaml
input_limits:
  max_message_length: 100000        # 100KB (chat messages)
  max_file_size_bytes: 52428800     # 50MB (artifact uploads)
  max_memory_entry_size: 10000      # 10KB (memory entries)
  max_tool_output_size: 1048576     # 1MB (tool outputs)
  max_batch_items: 100              # Batch operations
```

### Implementation Location
- `src/muxi/formation/overlord/input_validation.py` - New validation module
- `src/muxi/formation/overlord/overlord.py` - Integrate validation
- Formation config loading

### Implementation Notes
**Validation points:**
- `chat()` - Validate message length before processing
- `upload_artifact()` - Validate file size before processing
- Memory operations - Validate entry size before storage
- Tool execution - Validate output size after execution
- Batch operations - Validate batch count

**Error messages (user-friendly):**
```
Message too long: 125,430 characters (max: 100,000)

Try:
- Breaking into multiple messages
- Uploading content as a file
- Summarizing the key points
```

**HTTP layer:**
- Also enforce at server level (max_request_size_bytes)
- Return 413 Payload Too Large if exceeded

### Effort
~2 hours

---

## 6. PII Redaction in Observability

### Decision
**Always-on automatic redaction in `observe()` function**

### Rationale
- Existing utilities (`redact_sensitive_content()`) are not consistently applied
- Manual redaction is error-prone (easy to forget)
- Automatic redaction at emission point prevents all leakage
- No configuration - security by default
- No opt-out - if devs need raw data, access database directly

### Configuration
**No configuration** - Always enabled

### Implementation Location
- `src/muxi/services/observability/__init__.py` - Modify `observe()` function
- Use existing `src/muxi/utils/security.py` utilities

### Implementation Notes
```python
def observe(
    event_type: ...,
    level: EventLevel = EventLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> None:
    # ... existing checks ...
    
    # Automatic PII redaction
    if data:
        data = _redact_data_recursive(data)
    if description:
        description = redact_sensitive_content(description)
    
    # ... rest of observe logic ...

def _redact_data_recursive(obj: Any) -> Any:
    """Recursively redact PII in nested structures."""
    if isinstance(obj, str):
        return redact_sensitive_content(obj)
    elif isinstance(obj, dict):
        return {k: _redact_data_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        result = [_redact_data_recursive(item) for item in obj]
        return result if isinstance(obj, list) else tuple(result)
    else:
        return obj  # Numbers, bools, None, etc.
```

**Patterns redacted (via existing `redact_sensitive_content()`):**
- API keys (sk-, ghp-, AIza, xox-, etc.)
- Passwords and secrets
- Email addresses (partial: j****@example.com)
- Phone numbers
- Credit card numbers
- SSNs
- AWS credentials
- Database connection strings
- JWT tokens

**Performance:**
- Regex overhead per event (~0.1-1ms)
- Acceptable for async background emission
- No impact on main request flow (observe is already async)

### Effort
~4 hours

---

## Implementation Order

1. **Documentation** (this file) ✅
2. **Schema updates** (`formation.yaml`, `README.md`)
3. **Input limits** - Simplest, clear validation points
4. **Database timeout** - One-line change
5. **Workflow timeout** - Simple asyncio.timeout wrapper
6. **Credential salt** - Config refactoring
7. **PII redaction** - Helper function + integration
8. **Key rotation utility** - Standalone script (can be done last)

---

## Testing Strategy

### Unit Tests
- Input validation: Test boundary conditions (at limit, over limit, under limit)
- Timeout handling: Mock long-running operations
- PII redaction: Test all pattern types
- Salt configuration: Test default and custom values

### Integration Tests
- Workflow timeout: Long-running workflow with timeout
- Database timeout: Intentionally slow query (pg_sleep)
- Key rotation: Rotate salt, verify credentials still decrypt

### E2E Tests
- Formation with all new configs specified
- Formation with all defaults (backward compat)
- Error messages for limit violations

---

## Backward Compatibility

All enhancements are **fully backward compatible**:

1. **Workflow timeout**: Default 7200s (no change in behavior for existing formations)
2. **Database timeout**: Default 30s (most queries already complete in <1s)
3. **Credential salt**: Defaults to existing hardcoded value
4. **Input limits**: Defaults allow current usage patterns
5. **PII redaction**: Always on, but doesn't break functionality
6. **Key rotation**: Optional utility, no impact on existing deployments

**Existing formations continue to work without modification.**

---

## Deployment Notes

### Breaking Changes
**None** - All changes are additive with sensible defaults

### Migration Required
**None** - No database migrations, no credential re-encryption (unless using rotation utility)

### Documentation Updates
- Update formation schema documentation
- Add examples to formation templates
- Document key rotation utility usage
- Update security best practices guide

### Monitoring
- Track workflow timeout events (new observability event)
- Track database query timeout events (PostgreSQL logs)
- Track input validation errors (observability events)
- Track PII redaction patterns (for audit)

---

## Success Criteria

1. ✅ All 6 enhancements implemented
2. ✅ Schema updated with new parameters
3. ✅ Backward compatibility verified (existing formations work)
4. ✅ Tests passing (unit + integration + e2e)
5. ✅ Documentation complete
6. ✅ No regression in existing functionality
7. ✅ CODE_REVIEW_REPORT.md updated with completion status

---

## Future Considerations

**Deferred (not in scope):**
- Cache metrics/monitoring (nice-to-have)
- File size refactoring (deferred per user preference)
- API endpoint implementations (separate effort)
- Automatic key rotation scheduling (over-engineering)
- PII audit reports (utilities exist, manual usage)

**Revisit if:**
- Workflow timeouts prove insufficient (increase limit or add override)
- Database timeouts cause issues with legitimate queries (opt-out mechanism)
- Users request more granular input limits (per-endpoint configuration)

---

**End of Design Document**
