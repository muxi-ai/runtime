# Quick Test Guide - New API Endpoints

**Status:** Ready for testing!  
**Date:** 2025-10-23

## 🚀 Quick Start

### Option 1: Automated Test Script (Recommended)

```bash
# 1. Edit the script to add your API keys
nano test_api_endpoints.py
# Update ADMIN_KEY and CLIENT_KEY (find them in your formation's secrets.env)

# 2. Run the tests
python test_api_endpoints.py
```

### Option 2: Manual cURL Tests

**Get your API keys first:**
```bash
# They're in your formation directory
cat path/to/your/formation/secrets.env | grep API_KEY
```

---

## 🧪 Test Commands

### 1. Scheduler Jobs

```bash
# List all jobs
curl -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  http://localhost:8271/v1/scheduler/jobs

# Create a one-time job
curl -X POST \
  -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "one_time",
    "run_at": "2025-12-01T10:00:00Z",
    "message": "Test reminder",
    "user_id": "test-user"
  }' \
  http://localhost:8271/v1/scheduler/jobs

# Get job details (replace JOB_ID)
curl -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  http://localhost:8271/v1/scheduler/jobs/JOB_ID

# Delete job (replace JOB_ID)
curl -X DELETE \
  -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  http://localhost:8271/v1/scheduler/jobs/JOB_ID
```

---

### 2. User Identifiers

```bash
# Resolve an identifier (creates if not exists)
curl -H "X-Muxi-Client-Key: YOUR_CLIENT_KEY" \
  http://localhost:8271/v1/users/test-user@example.com

# List identifiers for a user (use muxi_user_id from above)
curl -H "X-Muxi-Client-Key: YOUR_CLIENT_KEY" \
  http://localhost:8271/v1/users/identifiers/usr_abc123

# Delete an identifier
curl -X DELETE \
  -H "X-Muxi-Client-Key: YOUR_CLIENT_KEY" \
  http://localhost:8271/v1/users/identifiers/test-user@example.com
```

---

### 3. Logging Destinations

```bash
# List destinations
curl -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  http://localhost:8271/v1/logging/destinations

# Create a file destination
curl -X POST \
  -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "transport": "file",
    "destination": "/tmp/test.log",
    "level": "DEBUG",
    "format": "jsonl"
  }' \
  http://localhost:8271/v1/logging/destinations

# Update destination (replace DEST_ID)
curl -X PATCH \
  -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"level": "INFO"}' \
  http://localhost:8271/v1/logging/destinations/DEST_ID

# Delete destination (replace DEST_ID)
curl -X DELETE \
  -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  http://localhost:8271/v1/logging/destinations/DEST_ID
```

---

### 4. Admin Log Streaming (SSE)

```bash
# Stream errors only
curl -N -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  "http://localhost:8271/v1/logs/stream?level=ERROR"

# Stream for specific user
curl -N -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  "http://localhost:8271/v1/logs/stream?user_id=alice"

# Stream specific request
curl -N -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  "http://localhost:8271/v1/logs/stream?request_id=req_abc123"

# Combine filters
curl -N -H "X-Muxi-Admin-Key: YOUR_ADMIN_KEY" \
  "http://localhost:8271/v1/logs/stream?user_id=alice&level=ERROR"
```

**Note:** The `-N` flag disables buffering for streaming responses.

---

## ✅ Expected Behaviors

### Scheduler Jobs
- ✅ List returns empty array initially
- ✅ POST creates job with auto-generated ID
- ✅ GET {id} returns job details
- ✅ DELETE removes job
- ❌ POST without required fields returns 400
- ❌ GET non-existent job returns 404

### User Identifiers
- ✅ GET /users/{identifier} creates user if not exists
- ✅ GET /users/identifiers/{user_id} lists identifiers
- ✅ DELETE removes identifier and invalidates cache
- ❌ DELETE non-existent identifier returns 404
- ❌ GET non-existent user_id returns 404

### Logging Destinations
- ✅ GET lists all destinations from formation config
- ✅ POST validates transport type and required fields
- ✅ PATCH updates level/format/enabled
- ✅ DELETE removes destination
- ❌ POST invalid transport returns 400
- ❌ POST file/stream without destination field returns 400

### Log Streaming
- ✅ Requires at least one filter parameter
- ✅ Returns SSE stream (text/event-stream)
- ✅ Initial connection event sent
- ✅ Graceful disconnection
- ❌ No filters returns 400 error

---

## 🐛 Troubleshooting

### "Service Unavailable" (503)
**Cause:** Scheduler not enabled or database not available  
**Fix:** Check your formation config has scheduler/database enabled

### "Unauthorized" (401)
**Cause:** Invalid or missing API key  
**Fix:** Check keys in `secrets.env` and ensure correct header name

### "Not Found" (404)
**Cause:** Resource doesn't exist  
**Fix:** Create the resource first or check ID

### "Bad Request" (400)
**Cause:** Missing required fields or validation error  
**Fix:** Check request body matches schema

### Scheduler jobs not persisting
**Note:** Current implementation uses in-memory storage  
**Enhancement:** Add persistence to formation config (see TODOs)

### Log streaming not showing events
**Note:** Framework is ready but needs observability event integration  
**Status:** Will show connection event, full events need observability hook

---

## 📊 Success Metrics

After running tests, you should see:

✅ **12 endpoints** responding correctly  
✅ **Proper error handling** (400, 404, 503)  
✅ **Consistent response format** (API envelope)  
✅ **Authentication working** (Admin/Client keys)  
✅ **ID generation** working (job IDs, dest IDs)  
✅ **Database queries** working (user identifiers)  

---

## 🎯 Next Steps

After testing:

1. ✅ **Verify all endpoints work** - Run through the test commands
2. 📝 **Note any issues** - Create tickets for bugs
3. 🚀 **Deploy to staging** - Test with real data
4. 📚 **Update docs** - Add examples to API docs
5. 👥 **User feedback** - Get real user input
6. 🔄 **Iterate** - Add sessions/buffer if needed

---

## 📞 Need Help?

Check these files:
- `schemas/api/FINAL_IMPLEMENTATION_SUMMARY.md` - Complete overview
- `schemas/api/formation-api-v1-final.yaml` - OpenAPI spec
- `test_api_endpoints.py` - Automated test script

---

**Happy Testing! 🧪**
