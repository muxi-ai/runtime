# API Endpoint Test Inventory

## Status: 24/84 endpoints tested (28.6% coverage)

**Test Files Created:**
- test_19a1_audit_logging.py - Audit endpoints (2)
- test_19b1_sop_endpoints.py - SOP endpoints (2) 
- test_19c1_scheduler_persistence.py - Scheduler validation (1)
- test_19d1_health_status.py - Health & status endpoints (6)
- test_19e1_chat_streaming.py - Chat streaming (3)
- test_19f1_agents_crud.py - Agents CRUD (5)
- test_19g1_memory_sessions.py - Memory & sessions (10)

## Legend
- ✅ Tested with comprehensive e2e test
- 🚧 Partial test coverage
- ❌ No test coverage
- 🌊 Streaming endpoint (requires special handling)

---

## Health/Status Endpoints (6/6 tested) ✅

| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | / | None | ✅ | test_19d1_health_status.py |
| GET | /v1 | None | ✅ | test_19d1_health_status.py |
| GET | /v1/health | None | ✅ | test_19d1_health_status.py |
| GET | /v1/config | Admin | ✅ | test_19d1_health_status.py |
| GET | /v1/formation | Admin | ✅ | test_19d1_health_status.py |
| GET | /v1/status | Admin | ✅ | test_19d1_health_status.py |

---

## Client Endpoints (requires client_key)

### Chat & Events (1/3 tested) 🌊
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| POST | /v1/chat | Client | ✅ 🌊 | test_19e1_chat_streaming.py |
| GET | /v1/events/{user_id} | Client | ❌ 🌊 | - |
| GET | /v1/stream/{user_id}/{session_id}/{request_id} | Client | ❌ 🌊 | - |

### SOPs (2/2 tested) ✅
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/sops | Client | ✅ | test_19b1_sop_endpoints.py |
| GET | /v1/sops/{sop_name} | Client | ✅ | test_19b1_sop_endpoints.py |

### Users (0/3 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/users/identifiers/{user_id} | Client | ❌ | - |
| DELETE | /v1/users/identifiers/{identifier} | Client | ❌ | - |
| GET | /v1/users/{identifier} | Client | ❌ | - |

### Memory (3/6 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/memories/{user_id} | Client | ❌ | - |
| POST | /v1/memories/{user_id} | Client | ❌ | - |
| DELETE | /v1/memories/{user_id}/{memory_id} | Client | ❌ | - |
| GET | /v1/memory/buffer/{user_id} | Client | ✅ | test_19g1_memory_sessions.py |
| DELETE | /v1/memory/buffer/{user_id} | Client | ❌ | - |
| DELETE | /v1/memory/buffer/{user_id}/{session_id} | Client | ✅ | test_19g1_memory_sessions.py |

### Sessions (4/4 tested) ✅
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/sessions/{user_id} | Client | ✅ | test_19g1_memory_sessions.py |
| GET | /v1/sessions/{user_id}/{session_id} | Client | ✅ | test_19g1_memory_sessions.py |
| DELETE | /v1/sessions/{user_id}/{session_id} | Client | ✅ | test_19g1_memory_sessions.py |
| GET | /v1/sessions/{user_id}/{session_id}/messages | Client | ✅ | test_19g1_memory_sessions.py |

### Jobs (0/2 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/jobs/{user_id} | Client | ❌ | - |
| DELETE | /v1/jobs/{user_id}/{job_id} | Client | ❌ | - |

### Triggers (0/2 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| POST | /v1/formations/{formation_id}/triggers/{trigger_name} | Client | ❌ | - |
| GET | /v1/formations/{formation_id}/triggers | Client | ❌ | - |

---

## Admin Endpoints (requires admin_key)

### Config & Status (0/3 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/config | Admin | ❌ | - |
| GET | /v1/formation | Admin | ❌ | - |
| GET | /v1/status | Admin | ❌ | - |

### Overlord (0/2 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/overlord | Admin | ❌ | - |
| GET | /v1/overlord/persona | Admin | ❌ | - |

### Agents (5/5 tested) ✅
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/agents | Admin | ✅ | test_19f1_agents_crud.py |
| POST | /v1/agents | Admin | ✅ | test_19f1_agents_crud.py |
| GET | /v1/agents/{agent_id} | Admin | ✅ | test_19f1_agents_crud.py |
| PATCH | /v1/agents/{agent_id} | Admin | ✅ | test_19f1_agents_crud.py |
| DELETE | /v1/agents/{agent_id} | Admin | ✅ | test_19f1_agents_crud.py |

### Secrets (0/4 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/secrets | Admin | ❌ | - |
| POST | /v1/secrets | Admin | ❌ | - |
| PUT | /v1/secrets/{key} | Admin | ❌ | - |
| DELETE | /v1/secrets/{key} | Admin | ❌ | - |

### Memory Admin (0/5 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/memory | Admin | ❌ | - |
| GET | /v1/memory/buffers | Admin | ❌ | - |
| DELETE | /v1/memory/buffers | Admin | ❌ | - |
| PATCH | /v1/memory | Admin | ❌ | - |
| DELETE | /v1/memory/{item} | Admin | ❌ | - |

### MCP (0/8 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/mcp | Admin | ❌ | - |
| PATCH | /v1/mcp | Admin | ❌ | - |
| GET | /v1/mcp/servers | Admin | ❌ | - |
| POST | /v1/mcp/servers | Admin | ❌ | - |
| GET | /v1/mcp/servers/{server_id} | Admin | ❌ | - |
| PATCH | /v1/mcp/servers/{server_id} | Admin | ❌ | - |
| DELETE | /v1/mcp/servers/{server_id} | Admin | ❌ | - |
| GET | /v1/mcp/tools | Admin | ❌ | - |
| POST | /v1/mcp/tools/call | Admin | ❌ | - |

### Scheduler (1/5 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/scheduler | Admin | ❌ | - |
| PATCH | /v1/scheduler | Admin | ❌ | - |
| GET | /v1/scheduler/jobs | Admin | ❌ | - |
| POST | /v1/scheduler/jobs | Admin | ✅ | test_19c1_scheduler_persistence.py (422 only) |
| GET | /v1/scheduler/jobs/{job_id} | Admin | ❌ | - |
| DELETE | /v1/scheduler/jobs/{job_id} | Admin | ❌ | - |

### Audit (2/2 tested) ✅
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/audit | Admin | ✅ | test_19a1_audit_logging.py |
| DELETE | /v1/audit | Admin | ✅ | test_19a1_audit_logging.py |

### Logging (0/5 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/logging | Admin | ❌ | - |
| GET | /v1/logging/destinations | Admin | ❌ | - |
| POST | /v1/logging/destinations | Admin | ❌ | - |
| PATCH | /v1/logging/destinations/{destination_id} | Admin | ❌ | - |
| DELETE | /v1/logging/destinations/{destination_id} | Admin | ❌ | - |

### Logs (0/1 tested) 🌊
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/logs/stream | Admin | ❌ 🌊 | - |

### LLM (0/3 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/llm/settings | Admin | ❌ | - |
| PATCH | /v1/llm/settings | Admin | ❌ | - |
| DELETE | /v1/llm/settings/{item} | Admin | ❌ | - |

### A2A (0/3 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/a2a | Admin | ❌ | - |
| PATCH | /v1/a2a/outbound | Admin | ❌ | - |
| DELETE | /v1/a2a/outbound/{item} | Admin | ❌ | - |

### Async Jobs (0/5 tested)
| Method | Path | Auth | Status | Test File |
|--------|------|------|--------|-----------|
| GET | /v1/async | Admin | ❌ | - |
| PATCH | /v1/async | Admin | ❌ | - |
| GET | /v1/async/jobs | Admin | ❌ | - |
| GET | /v1/async/jobs/{job_id} | Admin | ❌ | - |
| DELETE | /v1/async/jobs/{job_id} | Admin | ❌ | - |

---

## Summary

**Total Endpoints:** 84
**Tested:** 24 (28.6%)
**Untested:** 60 (71.4%)
**Streaming Endpoints:** 4 (1 tested, 3 untested)

## Priority Order for Testing

### P0 - Critical (must test first)
1. POST /v1/chat (streaming) - THE MAIN FEATURE
2. GET /v1/health
3. GET /v1/status
4. GET /v1/agents
5. POST /v1/agents

### P1 - High (core functionality)
6. GET /v1/memory/buffer/{user_id}
7. DELETE /v1/memory/buffer/{user_id}
8. GET /v1/sessions/{user_id}
9. GET /v1/sessions/{user_id}/{session_id}/messages
10. GET /v1/events/{user_id} (streaming)

### P2 - Medium (important features)
11-30. All memory, session, user, secret management endpoints

### P3 - Low (admin/config)
31+. All logging, MCP, A2A, async job endpoints
