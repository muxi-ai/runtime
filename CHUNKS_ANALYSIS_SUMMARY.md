# Comprehensive Chunks Analysis

====================================================================================================
CHUNK 1 ANALYSIS SUMMARY
====================================================================================================

Total events: 253
OK events: 199 (78.7%)
Problematic events: 54 (21.3%)

Issues by category:
  MISSING_DESCRIPTION           :  13 events
  NEEDS_REVIEW                  :   3 events
  REVIEW_DEBUG_GRANULAR         :  38 events

Level distribution:
  DEBUG   :  44 events ( 17.4%)
  INFO    : 142 events ( 56.1%)
  WARNING :  34 events ( 13.4%)
  ERROR   :  33 events ( 13.0%)

Sample problematic events (first 5 from each category):

MISSING_DESCRIPTION:
  1. ConversationEvents.A2A_MESSAGE_FAILED [ERROR]
     Location: src/muxi/services/a2a/client.py:236
     Issue: MISSING DESCRIPTION - Add meaningful description
  2. ConversationEvents.A2A_MESSAGE_SENT [INFO]
     Location: src/muxi/services/a2a/client.py:202
     Issue: MISSING DESCRIPTION - Add meaningful description
  3. ConversationEvents.AGENT_A2A [DEBUG]
     Location: src/muxi/formation/agents/agent.py:1600
     Issue: MISSING DESCRIPTION - Add meaningful description
  4. ConversationEvents.AGENT_MESSAGE_PROCESSING [INFO]
     Location: src/muxi/formation/agents/agent.py:883
     Issue: MISSING DESCRIPTION - Add meaningful description
  5. ConversationEvents.AGENT_PLANNING [DEBUG]
     Location: src/muxi/formation/agents/agent.py:1167
     Issue: MISSING DESCRIPTION - Add meaningful description
  ... and 8 more

NEEDS_REVIEW:
  1. ConversationEvents.AGENT_TOOL_CHAIN_COMPLETED [INFO]
     Location: src/muxi/formation/agents/agent.py:2134
     Issue: REVIEW - Consider DEBUG level for granular processing steps
  2. ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_COMPLETED [INFO]
     Location: src/muxi/formation/agents/agent.py:2080
     Issue: REVIEW - Consider DEBUG level for granular processing steps
  3. ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_STARTED [INFO]
     Location: src/muxi/formation/agents/agent.py:1778
     Issue: REVIEW - Consider DEBUG level for granular processing steps

REVIEW_DEBUG_GRANULAR:
  1. ConversationEvents.A2A_DISCOVERY_COMPLETED [DEBUG]
     Location: src/muxi/services/a2a/discovery.py:901
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  2. ConversationEvents.A2A_MESSAGE_SENT [DEBUG]
     Location: src/muxi/services/a2a/client.py:153
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  3. ConversationEvents.A2A_MESSAGE_SENT [DEBUG]
     Location: src/muxi/services/a2a/client.py:169
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  4. ConversationEvents.AGENT_PLANNING [DEBUG]
     Location: src/muxi/formation/agents/agent.py:1086
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  5. ConversationEvents.AGENT_PLANNING [DEBUG]
     Location: src/muxi/formation/agents/agent.py:1097
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  ... and 33 more

====================================================================================================
CHUNK 2 ANALYSIS SUMMARY
====================================================================================================

Total events: 253
OK events: 119 (47.0%)
Problematic events: 134 (53.0%)

Issues by category:
  MISSING_DESCRIPTION           :   4 events
  NEEDS_REVIEW                  :   2 events
  REPLACE_GENERIC               : 117 events
  REVIEW_DEBUG_GRANULAR         :  11 events

Level distribution:
  DEBUG   :  14 events (  5.5%)
  INFO    :  46 events ( 18.2%)
  WARNING :  76 events ( 30.0%)
  ERROR   : 117 events ( 46.2%)

Sample problematic events (first 5 from each category):

MISSING_DESCRIPTION:
  1. ConversationEvents.SESSION_CREATED [INFO]
     Location: src/muxi/formation/agents/knowledge/handler.py:184
     Issue: MISSING DESCRIPTION - Add meaningful description
  2. ErrorEvents.CONFIGURATION_ERROR [ERROR]
     Location: src/muxi/formation/overlord/overlord.py:1178
     Issue: MISSING DESCRIPTION - Add meaningful description
  3. ErrorEvents.CONNECTION_TIMEOUT [WARNING]
     Location: src/muxi/formation/workflow/executor.py:99
     Issue: MISSING DESCRIPTION - Add meaningful description
  4. ErrorEvents.CONNECTION_TIMEOUT [WARNING]
     Location: src/muxi/formation/workflow/executor.py:1541
     Issue: MISSING DESCRIPTION - Add meaningful description

NEEDS_REVIEW:
  1. ConversationEvents.RESPONSE_SYNTHESIZED [INFO]
     Location: src/muxi/formation/workflow/synthesis.py:482
     Issue: REVIEW - Consider DEBUG level for granular processing steps
  2. ErrorEvents.GENERIC_ERROR [WARNING]
     Location: src/muxi/formation/overlord/overlord.py:4161
     Issue: REVIEW - Generic event type, consider more specific event

REPLACE_GENERIC:
  1. ErrorEvents.INTERNAL_ERROR [DEBUG]
     Location: src/muxi/services/llm/llm.py:316
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  2. ErrorEvents.INTERNAL_ERROR [DEBUG]
     Location: src/muxi/services/llm/llm.py:709
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  3. ErrorEvents.INTERNAL_ERROR [ERROR]
     Location: src/muxi/formation/agents/agent.py:425
     Issue: REPLACE with ErrorEvents.KNOWLEDGE_SEARCH_FAILED
  4. ErrorEvents.INTERNAL_ERROR [ERROR]
     Location: src/muxi/formation/agents/agent.py:3416
     Issue: REPLACE with ErrorEvents.PLANNING_TEMPLATE_MISSING
  5. ErrorEvents.INTERNAL_ERROR [ERROR]
     Location: src/muxi/formation/agents/agent.py:3664
     Issue: REPLACE with ErrorEvents.A2A_MESSAGE_HANDLING_FAILED (alread
  ... and 112 more

REVIEW_DEBUG_GRANULAR:
  1. ConversationEvents.RESPONSE_CONVERSION_COMPLETED [DEBUG]
     Location: src/muxi/utils/response_converter.py:329
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  2. ConversationEvents.RESPONSE_CONVERSION_STARTED [DEBUG]
     Location: src/muxi/utils/response_converter.py:33
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  3. ConversationEvents.RESPONSE_CONVERSION_STARTED [DEBUG]
     Location: src/muxi/utils/response_converter.py:104
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  4. ConversationEvents.RESPONSE_CONVERSION_STARTED [DEBUG]
     Location: src/muxi/utils/response_converter.py:224
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  5. ConversationEvents.RESPONSE_CONVERSION_STARTED [DEBUG]
     Location: src/muxi/utils/response_converter.py:301
     Issue: REVIEW - DEBUG ConversationEvent, may be too granular for pr
  ... and 6 more

====================================================================================================
CHUNK 3 ANALYSIS SUMMARY
====================================================================================================

Total events: 253
OK events: 56 (22.1%)
Problematic events: 197 (77.9%)

Issues by category:
  ANTI_PATTERN                  :  33 events
  KEEP_INTENTIONAL              :   2 events
  MISNOMER                      :  81 events
  MISSING_DESCRIPTION           :   2 events
  NEEDS_REVIEW                  :   3 events
  REMOVE                        :  35 events
  REPLACE_GENERIC               :  41 events

Level distribution:
  DEBUG   :   4 events (  1.6%)
  INFO    :  51 events ( 20.2%)
  WARNING : 106 events ( 41.9%)
  ERROR   :  92 events ( 36.4%)

Sample problematic events (first 5 from each category):

ANTI_PATTERN:
  1. ErrorEvents.WARNING [DEBUG]
     Location: src/muxi/formation/artifacts/extractor.py:270
     Issue: ANTI-PATTERN - Don't use level (WARNING) as event type! Crea
  2. ErrorEvents.WARNING [WARNING]
     Location: src/muxi/formation/agents/knowledge/base.py:202
     Issue: ANTI-PATTERN - REPLACE with ErrorEvents.MARKITDOWN_INIT_FAIL
  3. ErrorEvents.WARNING [WARNING]
     Location: src/muxi/formation/agents/knowledge/base.py:317
     Issue: ANTI-PATTERN - REPLACE with ErrorEvents.KNOWLEDGE_SOURCE_MIS
  4. ErrorEvents.WARNING [WARNING]
     Location: src/muxi/formation/agents/knowledge/base.py:330
     Issue: ANTI-PATTERN - Don't use level (WARNING) as event type! Crea
  5. ErrorEvents.WARNING [WARNING]
     Location: src/muxi/formation/agents/knowledge/base.py:410
     Issue: ANTI-PATTERN - Don't use level (WARNING) as event type! Crea
  ... and 28 more

KEEP_INTENTIONAL:
  1. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/formation/server/server.py:154
     Issue: KEEP - Legitimate server start event
  2. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/utils/run_formation.py:77
     Issue: KEEP - Legitimate server start event

MISNOMER:
  1. ErrorEvents.RETRY_ATTEMPTED [ERROR]
     Location: src/muxi/formation/agents/knowledge/handler.py:483
     Issue: MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_SOURCE_ADD_FAI
  2. ErrorEvents.RETRY_ATTEMPTED [ERROR]
     Location: src/muxi/formation/agents/knowledge/handler.py:613
     Issue: MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_SEARCH_FAILED
  3. ErrorEvents.RETRY_ATTEMPTED [ERROR]
     Location: src/muxi/formation/agents/knowledge/handler.py:748
     Issue: MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_HANDLER_CREATI
  4. ErrorEvents.RETRY_ATTEMPTED [ERROR]
     Location: src/muxi/formation/agents/knowledge/handler.py:1461
     Issue: MISNOMER - No retry happening! Replace with specific error t
  5. ErrorEvents.RETRY_ATTEMPTED [ERROR]
     Location: src/muxi/formation/agents/knowledge/handler.py:1740
     Issue: MISNOMER - No retry happening! Replace with specific error t
  ... and 76 more

MISSING_DESCRIPTION:
  1. ErrorEvents.VALIDATION_FAILED [WARNING]
     Location: src/muxi/utils/user_resolution.py:94
     Issue: MISSING DESCRIPTION - Add meaningful description
  2. ErrorEvents.VALIDATION_FAILED [WARNING]
     Location: src/muxi/utils/user_resolution.py:304
     Issue: MISSING DESCRIPTION - Add meaningful description

NEEDS_REVIEW:
  1. ErrorEvents.VALIDATION_ERROR [ERROR]
     Location: src/muxi/formation/agents/agent.py:1191
     Issue: REVIEW - Generic event type, consider more specific event
  2. ErrorEvents.VALIDATION_ERROR [ERROR]
     Location: src/muxi/formation/workflow/decomposer.py:1171
     Issue: REVIEW - Generic event type, consider more specific event
  3. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/formation/server/server.py:166
     Issue: REVIEW - Check if legitimate server start or debug trace

REMOVE:
  1. ServerEvents.SERVER_STARTED [DEBUG]
     Location: src/muxi/formation/overlord/overlord.py:6460
     Issue: REMOVE - Misused as debug trace in overlord.py (not server s
  2. ServerEvents.SERVER_STARTED [DEBUG]
     Location: src/muxi/formation/overlord/overlord.py:6477
     Issue: REMOVE - Misused as debug trace in overlord.py (not server s
  3. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/formation/overlord/overlord.py:2579
     Issue: REMOVE - Misused as debug trace in overlord.py (not server s
  4. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/formation/overlord/overlord.py:2622
     Issue: REMOVE - Misused as debug trace in overlord.py (not server s
  5. ServerEvents.SERVER_STARTED [INFO]
     Location: src/muxi/formation/overlord/overlord.py:5462
     Issue: REMOVE - Misused as debug trace in overlord.py (not server s
  ... and 30 more

REPLACE_GENERIC:
  1. ErrorEvents.INTERNAL_ERROR [WARNING]
     Location: src/muxi/services/llm/llm.py:277
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  2. ErrorEvents.INTERNAL_ERROR [WARNING]
     Location: src/muxi/services/llm/llm.py:287
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  3. ErrorEvents.INTERNAL_ERROR [WARNING]
     Location: src/muxi/services/llm/llm.py:674
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  4. ErrorEvents.INTERNAL_ERROR [WARNING]
     Location: src/muxi/services/llm/llm.py:1360
     Issue: REPLACE with specific ErrorEvent type (INTERNAL_ERROR too ge
  5. ErrorEvents.INTERNAL_ERROR [WARNING]
     Location: src/muxi/services/memory/working.py:657
     Issue: REPLACE with ErrorEvents.MEMORY_OPERATION_FAILED
  ... and 36 more

====================================================================================================
CHUNK 4 ANALYSIS SUMMARY
====================================================================================================

Total events: 253
OK events: 234 (92.5%)
Problematic events: 19 (7.5%)

Issues by category:
  KEEP_INTENTIONAL              :   5 events
  MISSING_DESCRIPTION           :   7 events
  OTHER                         :   1 events
  REMOVE                        :   6 events

Level distribution:
  DEBUG   :  63 events ( 24.9%)
  INFO    : 104 events ( 41.1%)
  WARNING :  36 events ( 14.2%)
  ERROR   :  50 events ( 19.8%)

Sample problematic events (first 5 from each category):

KEEP_INTENTIONAL:
  1. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/initialization.py:277
     Issue: KEEP - Working memory config (distinct from buffer/persisten
  2. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/initialization.py:765
     Issue: KEEP - Clarification config not in InitEventFormatter
  3. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/formation.py:3146
     Issue: KEEP - Runtime event (not startup)
  4. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/formation.py:3177
     Issue: KEEP - Runtime event (not startup)
  5. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/formation.py:3192
     Issue: KEEP - Runtime event (not startup)

MISSING_DESCRIPTION:
  1. SystemEvents.A2A_AUTH_VALIDATION_FAILED [ERROR]
     Location: src/muxi/services/a2a/auth/inbound.py:586
     Issue: MISSING DESCRIPTION - Add meaningful description
  2. SystemEvents.A2A_REGISTRY_CONNECTED [INFO]
     Location: src/muxi/formation/overlord/overlord.py:1116
     Issue: MISSING DESCRIPTION - Add meaningful description
  3. SystemEvents.EXTENSION_LISTED [DEBUG]
     Location: src/muxi/extensions/base.py:209
     Issue: MISSING DESCRIPTION - Add meaningful description
  4. SystemEvents.EXTENSION_LOADED [ERROR]
     Location: src/muxi/extensions/base.py:103
     Issue: MISSING DESCRIPTION - Add meaningful description
  5. SystemEvents.EXTENSION_LOADED [ERROR]
     Location: src/muxi/extensions/base.py:140
     Issue: MISSING DESCRIPTION - Add meaningful description
  ... and 2 more

OTHER:
  1. SystemEvents.INITIALIZING [ERROR]
     Location: src/muxi/formation/initialization.py:636
     Issue: CONVERT to ErrorEvents.MCP_INITIALIZATION_FAILED (ERROR usin

REMOVE:
  1. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/artifacts/extractor.py:41
     Issue: REMOVE - DEBUG runtime trace (not initialization)
  2. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/overlord/overlord.py:2738
     Issue: REMOVE - DEBUG runtime trace (collection registration)
  3. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/overlord/overlord.py:2751
     Issue: REMOVE - DEBUG runtime trace (collection registration)
  4. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/formation/overlord/overlord.py:4188
     Issue: REMOVE - DEBUG runtime trace (file processing)
  5. SystemEvents.INITIALIZING [DEBUG]
     Location: src/muxi/services/memory/long_term.py:207
     Issue: REMOVE - DEBUG runtime trace (lazy loading)
  ... and 1 more

====================================================================================================
CHUNK 5 ANALYSIS SUMMARY
====================================================================================================

Total events: 249
OK events: 204 (81.9%)
Problematic events: 45 (18.1%)

Issues by category:
  KEEP_INTENTIONAL              :  13 events
  MISSING_DESCRIPTION           :   6 events
  NEEDS_REVIEW                  :  16 events
  REMOVE                        :  10 events

Level distribution:
  DEBUG   :  41 events ( 16.5%)
  INFO    : 128 events ( 51.4%)
  WARNING :  39 events ( 15.7%)
  ERROR   :  41 events ( 16.5%)

Sample problematic events (first 5 from each category):

KEEP_INTENTIONAL:
  1. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:97
     Issue: KEEP - Observability bootstrap (chicken-egg)
  2. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:234
     Issue: KEEP - LLM config not in InitEventFormatter
  3. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:553
     Issue: KEEP - Document processing not in InitEventFormatter
  4. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:651
     Issue: KEEP - Artifact service not in InitEventFormatter
  5. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:813
     Issue: KEEP - Document config not in InitEventFormatter
  ... and 8 more

MISSING_DESCRIPTION:
  1. SystemEvents.MCP_OVERLORD_REQUEST_CANCELLED [INFO]
     Location: src/muxi/services/mcp/handler.py:547
     Issue: MISSING DESCRIPTION - Add meaningful description
  2. SystemEvents.MCP_SERVER_DISCONNECTED [ERROR]
     Location: src/muxi/services/mcp/service.py:1090
     Issue: MISSING DESCRIPTION - Add meaningful description
  3. SystemEvents.MCP_SERVER_MAPPING_FAILED [WARNING]
     Location: src/muxi/services/mcp/handler.py:922
     Issue: MISSING DESCRIPTION - Add meaningful description
  4. SystemEvents.MCP_SERVER_OPERATIONS_CANCELLED [INFO]
     Location: src/muxi/services/mcp/handler.py:1038
     Issue: MISSING DESCRIPTION - Add meaningful description
  5. SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED [WARNING]
     Location: src/muxi/services/mcp/service.py:890
     Issue: MISSING DESCRIPTION - Add meaningful description
  ... and 1 more

NEEDS_REVIEW:
  1. SystemEvents.OPERATION_COMPLETED [DEBUG]
     Location: src/muxi/services/a2a/client.py:456
     Issue: REVIEW - Generic event type, consider more specific event
  2. SystemEvents.OPERATION_COMPLETED [DEBUG]
     Location: src/muxi/services/memory/extractor.py:513
     Issue: REVIEW - Generic event type, consider more specific event
  3. SystemEvents.OPERATION_COMPLETED [DEBUG]
     Location: src/muxi/services/memory/extractor.py:529
     Issue: REVIEW - Generic event type, consider more specific event
  4. SystemEvents.OPERATION_COMPLETED [DEBUG]
     Location: src/muxi/utils/user_resolution.py:81
     Issue: REVIEW - Generic event type, consider more specific event
  5. SystemEvents.OPERATION_COMPLETED [DEBUG]
     Location: src/muxi/utils/user_resolution.py:106
     Issue: REVIEW - Generic event type, consider more specific event
  ... and 11 more

REMOVE:
  1. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:339
     Issue: REMOVE - Redundant (InitEventFormatter section 2: Buffer mem
  2. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:456
     Issue: REMOVE - Redundant (InitEventFormatter section 4: Persistent
  3. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:604
     Issue: REMOVE - Redundant (InitEventFormatter section 5: MCP per-se
  4. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:708
     Issue: REMOVE - Redundant (InitEventFormatter section 8: Scheduler 
  5. SystemEvents.INITIALIZING [INFO]
     Location: src/muxi/formation/initialization.py:1077
     Issue: REMOVE - Redundant (InitEventFormatter section 4: Persistent
  ... and 5 more

