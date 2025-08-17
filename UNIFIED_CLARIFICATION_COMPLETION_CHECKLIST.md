# UnifiedClarificationSystem Completion Checklist

## Tasks to Complete Before Overlord Integration

### 1. ✅ Buffer Memory API
- [x] Using `kv_set/kv_get/kv_delete` is correct
- [ ] Update PRD to reflect actual API usage

### 2. ❌ Namespace Consistency
- [ ] Ensure all buffer memory keys use consistent format: `f"clarification:{request_id}"`
- [ ] Update `_store_state()` to use prefixed keys
- [ ] Update `_get_state()` to use prefixed keys  
- [ ] Update `_cleanup_state()` to use prefixed keys
- [ ] Update `has_active_clarification()` to use prefixed keys

### 3. ❌ Max Rounds Configuration
- [ ] Implement mode-specific max_rounds hierarchy from config
- [ ] Parse config structure: `max_rounds: {credential: 1, other: 3, ...}`
- [ ] Use mode-specific limits in `handle_response()`
- [ ] Default to sensible values if not configured

### 4. ❌ Token Detection Migration
- [ ] Move `looks_like_credential_token()` from ClarificationHandler to UnifiedClarificationSystem
- [ ] Move `extract_token_from_text()` from ClarificationHandler to UnifiedClarificationSystem
- [ ] Update credential handling flow to use these methods
- [ ] Remove dependency on ClarificationHandler

### 5. ❌ Remove ClarificationHandler Dependencies
- [ ] Remove ClarificationHandler initialization from overlord
- [ ] Remove cleanup task for stale clarifications (UnifiedClarificationSystem uses TTL)
- [ ] Remove `handle_clarification_response_v2` calls
- [ ] Delete ClarificationHandler class file once migration complete

### 6. ✅ State Management
- [x] State persistence in buffer memory
- [x] TTL-based expiration
- [x] Explicit cleanup on completion
- [x] Request ID as primary key

### 7. ✅ Multi-turn Support
- [x] `collected_info` array for accumulating responses
- [x] Depth tracking and max_depth checks
- [x] `_check_need_more()` logic
- [x] Context switch detection
- [x] Stop intent recognition

## Implementation Order

1. **First**: Fix namespace consistency (critical for state retrieval)
2. **Second**: Implement max_rounds configuration (needed for proper limits)
3. **Third**: Migrate token detection utilities (needed before removing ClarificationHandler)
4. **Fourth**: Remove ClarificationHandler completely
5. **Finally**: Integration with overlord (separate task)

## Code Locations

### Files to Modify:
- `/src/muxi/formation/overlord/clarification.py` - Main changes
- `/src/muxi/formation/overlord/overlord.py` - Remove ClarificationHandler references
- `/src/muxi/formation/overlord/clarification_handler.py` - To be deleted after migration

### Key Methods to Update:

#### In clarification.py:
```python
# Lines 231-248: Update these methods for namespace consistency
async def _store_state(self, request_id: str, state: Dict)
async def _get_state(self, request_id: str) -> Optional[Dict]
async def _cleanup_state(self, request_id: str)
async def has_active_clarification(self, request_id: str) -> bool

# Lines 39-40: Update config parsing for max_rounds hierarchy
def __init__(self, overlord, config=None):
    # Parse max_rounds as dict structure
    
# Add new methods for token detection (from ClarificationHandler)
async def looks_like_credential_token(self, message: str) -> bool
async def extract_token_from_text(self, message: str) -> Optional[str]
```

## Testing Requirements

After completion, verify:
1. State can be stored and retrieved with consistent keys
2. Mode-specific max_rounds limits are respected
3. Token detection works for credential responses
4. No references to ClarificationHandler remain
5. All existing tests still pass

## Notes

- Buffer memory `kv_*` methods are correct - PRD needs update, not code
- Namespace prefix ensures no collision with other buffer memory usage
- Max rounds hierarchy allows different limits per clarification mode
- Token detection is essential for credential flow, must be preserved during migration