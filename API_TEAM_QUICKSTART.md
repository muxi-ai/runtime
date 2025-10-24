# API Team Quick Start Guide to 100%

## 🎯 Goal: 15/23 (65%) → 23/23 (100%)

**Current Status**: 15 tests passing, 8 blocked by bugs  
**Your Mission**: Fix bugs to unblock tests  
**Estimated Time**: 2 weeks with focused effort

---

## ⚡ Quick Start (Get to 78% in 1-2 hours!)

### The Problem
Three API endpoints return lists directly, but the `APIResponse` schema expects dicts. This causes ValidationError (500).

### The Fix Pattern
```python
# ❌ BEFORE (causes 500 error)
return APIResponse(
    success=True,
    data=servers  # List!
)

# ✅ AFTER (works correctly)
return APIResponse(
    success=True,
    data={"servers": servers}  # Dict!
)
```

### Files to Fix

1. **GET /v1/mcp/servers**
   - File: `src/muxi/formation/server/routes/admin/mcp.py`
   - Change: Wrap servers list in dict
   - Test: `e2e/tests/19_api/test_19n1_mcp.py`

2. **GET /v1/memory/buffers**
   - File: `src/muxi/formation/server/routes/admin/memory.py`
   - Change: Wrap buffers list in dict
   - Test: `e2e/tests/19_api/test_19o1_memory_admin.py`

3. **GET /v1/async/jobs**
   - File: `src/muxi/formation/server/routes/admin/async_ops.py` (or similar)
   - Change: Wrap jobs list in dict
   - Test: `e2e/tests/19_api/test_19s1_async_jobs.py`

### Verify Your Fix

```bash
cd e2e/tests/19_api
python3 test_19n1_mcp.py          # Should pass
python3 test_19o1_memory_admin.py # Should pass  
python3 test_19s1_async_jobs.py   # Should pass

# Run all tests
bash validate_all.sh              # Should show 18/23 (78%)
```

**🎉 After this fix: 18/23 passing (78%)!**

---

## 📋 All Bugs Prioritized

### 🔴 Priority 1: List-Wrapping (1-2 hours) → 78%
- [ ] Bug #8: GET /v1/mcp/servers
- [ ] Bug #9: GET /v1/memory/buffers  
- [ ] Bug #10: GET /v1/async/jobs

### 🟡 Priority 2: Critical Bugs (1-2 days) → 91%
- [ ] Bug #1: Chat non-streaming timeout
- [ ] Bug #3: DELETE buffer memory crash (500)
- [ ] Bug #4: Secrets POST crash (500)

### 🟢 Priority 3: Infrastructure (2-3 days) → 96%
- [ ] Bug #5: Setup test database for persistent memory
- [ ] Bug #7: Scheduler endpoint handling

### 🔵 Priority 4: Features (1 week) → 100%
- [ ] Bug #6: Implement jobs feature
- [ ] Bug #13: Fix stream import error

---

## 🔍 Detailed Bug Information

See `API_FIX_ROADMAP_TO_100.md` for:
- Exact code examples for each fix
- File locations
- Test reproduction steps
- Expected vs actual behavior
- Fix verification commands

---

## 🧪 Testing Workflow

### 1. Fix a Bug
```bash
# Edit the file with the bug
vim src/muxi/formation/server/routes/admin/mcp.py
```

### 2. Run the Affected Test
```bash
cd e2e/tests/19_api
python3 test_19n1_mcp.py
```

### 3. Verify Pass
```
✅ Test Result: 🎉 SUCCESS
```

### 4. Run All Tests
```bash
bash validate_all.sh
```

### 5. Commit Your Fix
```bash
git add src/muxi/formation/server/routes/admin/mcp.py
git commit -m "fix(api): wrap MCP servers list in dict (bug #8)

- Fixed GET /v1/mcp/servers ValidationError
- Returns {\"servers\": [...]} instead of [...]
- Test test_19n1_mcp now passes

Tests: 16/23 passing"
```

---

## 📊 Progress Dashboard

Run this to see current progress:
```bash
cd e2e/tests/19_api
bash validate_all.sh
```

Output will show:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Passed:  18
  ❌ Failed:  5
  📦 Total:   23

  🎯 Pass Rate: 78%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🎯 Milestones

- **78%** (18/23) - List-wrapping bugs fixed ✨
- **91%** (21/23) - Critical bugs fixed
- **96%** (22/23) - Infrastructure setup
- **100%** (23/23) - All features complete 🎉

---

## 📚 Documentation

- `API_BUGS_DISCOVERED.md` - All 13 bugs with reproduction steps
- `API_FIX_ROADMAP_TO_100.md` - Detailed fix guide with code examples
- `API_TEST_COMPLETE_JOURNEY.md` - How we got to 65%

---

## 🆘 Getting Help

### Bug is Unclear?
Check `API_BUGS_DISCOVERED.md` for:
- Full error messages
- Reproduction steps
- Expected vs actual behavior

### Don't Know Where the Code Is?
Search for the endpoint:
```bash
cd src
grep -r "GET /v1/mcp/servers" .
grep -r "@router.get.*mcp" .
```

### Test Keeps Failing?
1. Check if port 8271 is in use: `lsof -ti :8271 | xargs kill -9`
2. Look at test output for error messages
3. Check `API_BUGS_DISCOVERED.md` for known issues

---

## 🚀 Let's Go!

**Start here**: Fix the 3 list-wrapping bugs (1-2 hours)  
**Result**: 78% pass rate immediately  
**Next**: Follow roadmap to 100%

Good luck! 🎯

---

## 💡 Pro Tips

1. **Fix bugs in order** - Bugs #8-10 are easiest
2. **Run tests frequently** - Catch issues early
3. **Commit often** - One bug fix per commit
4. **Use validation script** - Track overall progress
5. **Ask questions** - Documentation has all the details

---

**Questions?** Check the documentation files or search the codebase!
