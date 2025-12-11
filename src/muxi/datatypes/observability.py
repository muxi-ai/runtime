"""
MUXI Observability System Types

This module contains all the enum types and data classes for the observability system,
including event types, levels, and data structures.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set, List, Any


class EventLevel(Enum):
    """Event severity levels for observability events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SystemEvents(Enum):
    """System infrastructure events for server monitoring and operations (routed to stdout)."""

    # REMOVED: INITIALIZING - replaced by InitEventFormatter banner
    # REMOVED: SERVICE_STARTED - replaced by InitEventFormatter completion message

    CLEANUP = "cleanup"
    # When server is cleaning up

    # ===================================================================
    # LLM SYSTEM EVENTS
    # ===================================================================
    LLM_INITIALIZED = "llm.initialized"
    # When LLM instance is initialized

    LLM_CACHE_CLEARED = "llm.cache.cleared"
    # When LLM response cache is cleared

    LLM_CACHE_CONFIGURED = "llm.cache.configured"
    # When LLM cache TTL is configured

    LLM_STATISTICS_RESET = "llm.statistics.reset"
    # When LLM statistics and circuit breakers are reset

    # ===================================================================
    # MCP RETRY EVENTS
    # ===================================================================
    MCP_RETRY_ATTEMPTED = "mcp.retry.attempted"
    # When MCP operation retry is attempted

    # ===================================================================
    # USER MANAGEMENT EVENTS
    # ===================================================================
    USER_RESOLVED = "user.resolved"
    # When user identifier is resolved to existing user

    USER_CREATED = "user.created"
    # When new user is created

    USER_IDENTIFIERS_ASSOCIATED = "user.identifiers.associated"
    # When identifiers are associated with user

    # ===================================================================
    # DOCUMENT CROSS-REFERENCE EVENTS
    # ===================================================================
    CROSS_REFERENCE_MANAGER_INITIALIZED = "cross_reference.manager.initialized"
    # When document cross-reference manager is initialized

    CROSS_REFERENCE_ADDED = "cross_reference.added"
    # When document cross-reference is added

    CROSS_REFERENCES_LOADED = "cross_reference.loaded"
    # When document cross-references are loaded from storage

    # ===================================================================
    # A2A CLEANUP EVENTS
    # ===================================================================
    A2A_HTTPX_CLEANUP = "a2a.httpx.cleanup"
    # When A2A service httpx client is cleaned up

    OVERLORD_SHUTDOWN = "overlord.shutdown"
    # When overlord is shutting down gracefully

    SECURITY_CONFIGURATION_WARNING = "security.configuration.warning"
    # When a security configuration issue is detected (e.g., weak encryption key)

    # ===================================================================
    # MCP SYSTEM EVENTS
    # ===================================================================
    # REMOVED: MCP_SERVER_PROCESS_STARTED - replaced by InitEventFormatter

    MCP_SERVER_PROCESS_FAILED = "mcp.server.process.failed"
    # When MCP server subprocess fails to start or crashes

    MCP_SERVER_REGISTERED = "mcp.server.registration.completed"
    # When MCP server is successfully registered

    MCP_SERVER_REGISTRATION_FAILED = "mcp.server.registration.failed"
    # When MCP server registration fails

    # REMOVED: MCP_SERVER_REGISTRATION_STARTED - replaced by InitEventFormatter
    # REMOVED: MCP_SERVER_REGISTRATION_COMPLETED - replaced by InitEventFormatter
    # REMOVED: MCP_TOOL_DISCOVERY_COMPLETED - included in InitEventFormatter output
    # REMOVED: MCP_SERVER_CONNECTING - replaced by InitEventFormatter
    # REMOVED: MCP_SERVER_CONNECTED - replaced by InitEventFormatter

    # Connection lifecycle events (runtime only)

    MCP_SERVER_CONNECTION_FAILED = "mcp.server.connection_failed"
    # When MCP server connection fails

    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
    # When MCP server disconnects

    MCP_SERVER_DISCONNECTION_FAILED = "mcp.server.disconnection_failed"
    # When MCP server disconnection fails

    MCP_SERVER_RECONNECTING = "mcp.server.reconnecting"
    # When attempting to reconnect to MCP server

    MCP_SERVER_RECONNECTED = "mcp.server.reconnected"
    # When MCP server successfully reconnects after disconnection

    MCP_SERVER_CONNECTION_LOST = "mcp.server.connection_lost"
    # When connection to MCP server is lost

    # Deregistration events
    MCP_SERVER_UNREGISTERED = "mcp.server.unregistered"
    # When MCP server is successfully unregistered

    MCP_SERVER_UNREGISTRATION_FAILED = "mcp.server.unregistration_failed"
    # When MCP server unregistration fails

    # Message handling events
    MCP_MESSAGE_SENT = "mcp.message.sent"
    # When MCP message is sent to server

    MCP_MESSAGE_RECEIVED = "mcp.message.received"
    # When MCP message is received from server

    MCP_MESSAGE_FAILED = "mcp.message.failed"
    # When MCP message handling fails

    MCP_SERVER_MAPPING_INCONSISTENT = "mcp.server.mapping.inconsistent"
    # When MCP server name mapping is inconsistent

    MCP_TOOL_FALLBACK_USED = "mcp.tool.fallback.used"
    # When MCP tool execution falls back to alternative

    MCP_TRANSPORT_CACHE_CLEARED = "mcp.transport.cache.cleared"
    # When MCP transport cache is cleared

    # ===================================================================
    # MCP TRANSPORT EVENTS (Added for Streamable HTTP implementation)
    # ===================================================================
    # REMOVED: MCP_TRANSPORT_DETECTED - included in InitEventFormatter MCP output

    MCP_TRANSPORT_DETECTION_FAILED = "mcp.transport.detection.failed"
    # When transport auto-detection fails

    MCP_TRANSPORT_ATTEMPT = "mcp.transport.attempt"
    # When attempting to connect with a specific transport

    MCP_TRANSPORT_FAILED = "mcp.transport.failed"
    # When specific transport connection fails

    MCP_TRANSPORT_FALLBACK_SUCCESS = "mcp.transport.fallback.success"
    # When fallback transport succeeds after primary fails

    # ===================================================================
    # AGENT SYSTEM EVENTS
    # ===================================================================
    # REMOVED: AGENT_INITIALIZED - replaced by InitEventFormatter per-agent output

    # ===================================================================
    # A2A SYSTEM EVENTS
    # ===================================================================
    # REMOVED: A2A_CONFIG_LOAD_STARTED - replaced by InitEventFormatter
    # REMOVED: A2A_CONFIG_LOAD_COMPLETED - replaced by InitEventFormatter

    A2A_CREDENTIAL_LOADED = "a2a.credential.loaded"
    # When A2A credentials are loaded from storage

    A2A_CREDENTIALS_LOAD_FAILED = "a2a.credentials.load_failed"
    # When A2A credential loading fails

    A2A_CARD_GENERATOR_INITIALIZED = "a2a.card.generator.initialized"
    # When A2A agent card generator is set up

    A2A_AUTH_INITIALIZED = "a2a.auth.initialized"
    # When A2A authentication system is initialized

    A2A_AUTH_VALIDATING = "a2a.auth.validating"
    # When validating A2A authentication credentials

    A2A_AUTH_VALIDATED = "a2a.auth.validated"
    # When A2A authentication is successful

    A2A_AUTH_VALIDATION_FAILED = "a2a.auth.validation_failed"
    # When A2A authentication fails

    A2A_REGISTRY_CLIENT_INITIALIZED = "a2a.registry.client.initialized"
    # When A2A registry client is created

    A2A_REGISTRY_CONNECTED = "a2a.registry.connected"
    # When connection to A2A registry is established

    A2A_REGISTRY_DISCONNECTED = "a2a.registry.disconnected"
    # When A2A registry connection is lost

    A2A_REGISTRY_HEALTH_CHECK_COMPLETED = "a2a.registry.health_check.completed"
    # When A2A registry health check finishes

    A2A_HEALTH_CHECK_STARTED = "a2a.health.check.started"
    # When starting A2A system health check

    A2A_HEALTH_CHECK_COMPLETED = "a2a.health.check.completed"
    # When A2A health check completes successfully

    A2A_HEALTH_CHECK_FAILED = "a2a.health.check.failed"
    # When A2A health check fails

    A2A_REGISTERED = "a2a.registration.completed"
    # When agent is successfully registered with A2A registry

    A2A_REGISTRATION_FAILED = "a2a.registration.failed"
    # When agent registration with A2A registry fails

    A2A_DEREGISTERED = "a2a.deregistration.completed"
    # When agent is successfully deregistered from A2A registry

    A2A_DEREGISTRATION_FAILED = "a2a.deregistration.failed"
    # When agent deregistration from A2A registry fails

    # REMOVED: A2A_SERVER_STARTED - replaced by InitEventFormatter

    A2A_SERVER_STOPPED = "a2a.server.stopped"
    # When A2A server component stops

    A2A_SERVER_FAILED = "a2a.server.failed"
    # When A2A server component fails

    A2A_DISCOVERY_STARTED = "a2a.discovery.started"
    # When starting A2A agent discovery process

    A2A_DISCOVERY_STOPPED = "a2a.discovery.stopped"
    # When A2A agent discovery process stops

    A2A_DISCOVERY_COMPLETED = "a2a.discovery.completed"
    # When A2A agent discovery process completes

    A2A_DISCOVERY_FAILED = "a2a.discovery.failed"
    # When A2A agent discovery process fails

    A2A_AGENT_REGISTERED = "a2a.agent.registered"
    # When external agent registers with our A2A system

    A2A_AGENT_DEREGISTERED = "a2a.agent.deregistered"
    # When external agent deregisters from our A2A system

    A2A_CARD_GENERATING = "a2a.card.generating"
    # When starting to generate A2A agent card

    A2A_CARD_GENERATED = "a2a.card.generated"
    # When A2A agent card generation completes

    A2A_CARD_EXPORTING = "a2a.card.exporting"
    # When starting to export A2A agent card

    A2A_CARD_EXPORTED = "a2a.card.exported"
    # When A2A agent card export completes

    A2A_AGENT_REGISTRATIONS_COMPLETED = "a2a.agent.registrations.completed"
    # When bulk A2A agent registrations complete

    A2A_REGISTRATION_COMPLETED = "a2a.registration.completed"
    # When individual A2A agent registration completes

    A2A_DEREGISTRATION_STARTED = "a2a.deregistration.started"
    # When A2A agent deregistration begins

    A2A_CREDENTIAL_REMOVED = "a2a.credential.removed"
    # When A2A credentials are removed for an agent

    A2A_MESSAGE_PARSING = "a2a.message.parsing"
    # When A2A message format parsing/fallback occurs

    # ===================================================================
    # CREDENTIAL MANAGEMENT
    # ===================================================================
    CREDENTIAL_CONFIGURED = "credential.configured"
    # When credentials are configured for a service

    CREDENTIAL_UPDATE = "credential.update"
    # When credentials are updated for a user/service

    # ===================================================================
    # AGENT LIFECYCLE EVENTS
    # ===================================================================
    AGENT_DEREGISTRATION_COMPLETED = "agent.deregistration.completed"
    # When agent is successfully deregistered/removed

    # ===================================================================
    # CONFIGURATION & STARTUP EVENTS
    # ===================================================================
    CONFIG_FORMATION_LOADED = "config.formation.loaded"
    # When formation configuration file is loaded

    CONFIG_AGENT_LOADED = "config.agent.loaded"
    # When agent configuration is loaded

    CONFIG_MCP_LOADED = "config.mcp.loaded"
    # When MCP server configuration is loaded

    CONFIG_A2A_LOADED = "config.a2a.loaded"
    # When A2A configuration is loaded

    # REMOVED: OVERLORD_INITIALIZING - replaced by InitEventFormatter banner
    # REMOVED: OVERLORD_STARTED - replaced by InitEventFormatter
    # REMOVED: CACHE_MANAGER_STARTED - too granular, internal detail
    # REMOVED: MEMORY_OPTIMIZER_STARTED - too granular, internal detail

    # ===================================================================
    # AUTHENTICATION & SECURITY EVENTS
    # ===================================================================
    # REMOVED: AUTH_MANAGER_INITIALIZED - too granular, internal detail
    # REMOVED: INBOUND_AUTH_INITIALIZED - too granular, internal detail

    # ===================================================================
    # EKNOWLEDGE SYSTEM EVENTS
    # ===================================================================
    KNOWLEDGE_SOURCE_LOADED = "knowledge.source.loaded"
    # When knowledge source is successfully loaded

    KNOWLEDGE_SOURCE_FAILED = "knowledge.source.failed"
    # When knowledge source loading fails

    # ===================================================================
    # INFRASTRUCTURE MONITORING (MOVED FROM CONVERSATIONEVENTs)
    # ===================================================================
    RESOURCE_USAGE_MEASURED = "resource.usage.measured"
    # When system resource usage is measured

    RESOURCE_ALLOCATED = "resource.allocated"
    # When system resources are allocated

    # ===================================================================
    # EXTENSION MANAGEMENT
    # ===================================================================
    EXTENSION_LOADED = "extension.loaded"
    # When extension is successfully loaded

    EXTENSION_FAILED = "extension.failed"
    # When extension loading or operation fails

    EXTENSION_LISTED = "extension.listed"
    # When extension listing operation completes

    EXTENSION_LISTING_FAILED = "extension.listing.failed"
    # When extension listing operation fails

    # ===================================================================
    # MEMORY SYSTEM OPERATIONS
    # ===================================================================
    MEMORY_CLEAR = "memory.clear"
    # When memory system is cleared

    MEMORY_DELETION_COMPLETED = "memory.deletion.completed"
    # When memory deletion operation completes

    MEMORY_DELETION_FAILED = "memory.deletion.failed"
    # When memory deletion operation fails

    # ===================================================================
    # PERFORMANCE MONITORING
    # ===================================================================
    PERFORMANCE_DURATION_RECORDED = "performance.duration.recorded"
    # When performance timing is recorded

    PERFORMANCE_OPTIMIZED = "performance.optimized"
    # When performance optimization is applied

    # ===================================================================
    # SECRET MANAGEMENT OPERATIONS
    # ===================================================================
    SECRET_OPERATION_COMPLETED = "secret.operation.completed"
    # When secret operation (store/retrieve/import/export) completes
    # (with operation_type: "storage", "retrieval", "import", etc. in event data)

    SECRET_OPERATION_FAILED = "secret.operation.failed"
    # When secret operation (store/retrieve/import/export) fails

    SECRET_LISTING_COMPLETED = "secret.listing.completed"
    # When secret listing operation completes

    SECRET_LISTING_FAILED = "secret.listing.failed"
    # When secret listing operation fails

    # ===================================================================
    # AGENT MANAGEMENT OPERATIONS
    # ===================================================================
    AGENT_ADDED = "agent.added"
    # When agent is dynamically added via API

    AGENT_UPDATED = "agent.updated"
    # When agent configuration is updated via API

    AGENT_REMOVED = "agent.removed"
    # When agent is removed via API

    # ===================================================================
    # GENERAL OPERATIONS
    # ===================================================================
    SERVICE_STARTED = "service.started"
    # When a service or operation starts (generic runtime event)

    OPERATION_COMPLETED = "operation.completed"
    # When a named operation completes successfully (with timing)

    SYSTEM_ACTION = "system.action"
    # Generic system action event for various operations

    # ===================================================================
    # DATABASE/STORAGE OPERATIONS
    # ===================================================================
    DB_CONNECTION_STARTED = "db.connection.started"
    # When database connection is initiated

    DB_CONNECTION_FAILED = "db.connection.failed"
    # When database connection fails

    DATABASE_TYPE_FALLBACK = "db.type.fallback"
    # When database falls back to different type/mode

    # ===================================================================
    # SCHEDULER SYSTEM OPERATIONS
    # ===================================================================
    # REMOVED: SCHEDULER_SERVICE_INITIALIZED - replaced by InitEventFormatter
    # REMOVED: SCHEDULER_MANAGER_INITIALIZED - too granular, internal detail
    # REMOVED: SCHEDULER_PARSER_INITIALIZED - too granular, internal detail
    # REMOVED: SCHEDULER_DATABASE_INITIALIZED - too granular, internal detail
    # REMOVED: DATABASE_MANAGER_INITIALIZED - replaced by InitEventFormatter persistent memory message
    # REMOVED: DATABASE_TABLES_CREATED - replaced by InitEventFormatter schema ready message

    SCHEDULER_CACHE_CLEANUP = "scheduler.cache.cleanup"
    # When scheduler cache is cleaned up

    SCHEDULER_CIRCUIT_BREAKER_ACTIVATED = "scheduler.circuit_breaker.activated"
    # When scheduler circuit breaker is activated

    SCHEDULER_CIRCUIT_BREAKER_STATE_CHANGE = "scheduler.circuit_breaker.state_change"
    # When scheduler circuit breaker changes state

    SCHEDULER_CLEANUP_BATCH = "scheduler.cleanup.batch"
    # When scheduler performs batch cleanup

    SCHEDULER_PROMPT_COMPARISON = "scheduler.prompt.comparison"
    # When scheduler compares prompts for deduplication

    CRON_EXPRESSION_FIXED = "scheduler.cron.expression.fixed"
    # When invalid cron expression is automatically fixed

    CRON_TIMEZONE_CONVERTED = "scheduler.cron.timezone.converted"
    # When cron expression timezone is converted

    # ===================================================================
    # NETWORK/COMMUNICATION INFRASTRUCTURE
    # ===================================================================
    # REMOVED: NETWORK_INTERFACE_INITIALIZED - too granular, not used

    NETWORK_INTERFACE_FAILED = "network.interface.failed"
    # When network interface initialization fails

    # ===================================================================
    # RESILIENCE SYSTEM EVENTS
    # ===================================================================
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"
    # When circuit breaker opens due to failures

    CIRCUIT_BREAKER_CLOSED = "circuit_breaker.closed"
    # When circuit breaker closes after recovery

    CIRCUIT_BREAKER_HALF_OPEN = "circuit_breaker.half_open"
    # When circuit breaker enters half-open state for testing

    CIRCUIT_BREAKER_FALLBACK_TRIGGERED = "circuit_breaker.fallback.triggered"
    # When circuit breaker triggers fallback function

    CIRCUIT_BREAKER_FAILURE_RECORDED = "circuit_breaker.failure.recorded"
    # When circuit breaker records a failure

    CIRCUIT_BREAKER_SUCCESS_RECORDED = "circuit_breaker.success.recorded"
    # When circuit breaker records a success

    CIRCUIT_BREAKER_FORCED_OPEN = "circuit_breaker.forced.open"
    # When circuit breaker is manually forced open

    CIRCUIT_BREAKER_FORCED_CLOSED = "circuit_breaker.forced.closed"
    # When circuit breaker is manually forced closed

    CIRCUIT_BREAKER_RESET = "circuit_breaker.reset"
    # When circuit breaker state is reset


class ConversationEvents(Enum):
    """Comprehensive event types for MUXI observability covering complete request lifecycle."""

    # ===================================================================
    # SESSION MANAGEMENT
    # ===================================================================
    SESSION_CREATED = "session.created"
    # When new user session is established

    SESSION_ENDED = "session.ended"
    # When user session is terminated normally

    SESSION_EXPIRED = "session.expired"
    # When user session expires due to inactivity

    # ===================================================================
    # REQUEST INGESTION & VALIDATION
    # ===================================================================
    REQUEST_RECEIVED = "request.received"
    # When incoming request is received by the system

    REQUEST_PROCESSING = "request.processing"
    # When request enters processing pipeline

    REQUEST_VALIDATED = "request.validated"
    # When request passes validation checks

    REQUEST_DENIED_AUTH = "request.denied.auth"
    # When request is rejected due to authentication failure

    REQUEST_DENIED_RATE_LIMIT = "request.denied.rate_limit"
    # When request is rejected due to rate limiting

    REQUEST_DENIED_VALIDATION = "request.denied.validation"
    # When request is rejected due to validation errors

    SECURITY_VIOLATION = "security.violation"
    # When a security threat is detected and blocked

    REQUEST_FAILED = "request.failed"  # Error state
    # When request processing fails with error

    REQUEST_COMPLETED = "request.completed"  # Success state
    # When request processing completes successfully

    REQUEST_MODE_CHANGED = "request.mode.changed"
    # When request processing mode is forced to change (e.g., async→sync due to missing webhook)

    REQUEST_MODE_RESOLVED = "request.mode.resolved"
    # When conflicting request modes are resolved (e.g., async + streaming conflict)

    REQUEST_ID_REUSED = "request.id.reused"
    # When existing request_id is reused for multi-turn clarification

    REQUEST_CONTEXT_LOADED = "request.context.loaded"
    # When request context is loaded from memory (buffer + long-term)

    REQUEST_NON_ACTIONABLE = "request.non_actionable"
    # When request is identified as non-actionable (greeting, acknowledgment) and uses fast path

    REQUEST_QUEUED_ASYNC = "request.queued.async"
    # When request is queued for asynchronous processing

    # ===================================================================
    # MULTI-MODAL CONTENT PROCESSING
    # ===================================================================
    DOCUMENT_PROCESSING_STARTED = "document.processing.started"
    # When document processing begins

    DOCUMENT_PROCESSING_COMPLETED = "document.processing.completed"
    # When document processing completes successfully

    DOCUMENT_PROCESSING_FAILED = "document.processing.failed"
    # When document processing fails

    CONTENT_EXTRACTION_STARTED = "content.extraction.started"
    # When content extraction from media begins

    CONTENT_EXTRACTION_COMPLETED = "content.extraction.completed"
    # When content extraction completes successfully

    CONTENT_EXTRACTION_FAILED = "content.extraction.failed"
    # When content extraction fails

    CONTENT_PROCESSED = "content.processed"
    # When content processing completes

    CONTENT_RETRIEVED = "content.retrieved"
    # When content is retrieved from storage

    CONTENT_IMAGE_ANALYZED = "content.image.analyzed"
    # When image analysis completes

    CONTENT_AUDIO_TRANSCRIBED = "content.audio.transcribed"
    # When audio transcription completes

    # ===================================================================
    # OVERLORD ORCHESTRATION
    # ===================================================================
    OVERLORD_ROUTING_STARTED = "overlord.routing.started"
    # When overlord begins routing decision process

    OVERLORD_ROUTING_COMPLETED = "overlord.routing.completed"
    # When overlord completes routing decision

    OVERLORD_ROUTING_FAILED = "overlord.routing.failed"
    # When overlord routing process fails

    OVERLORD_AGENT_SELECTION_STARTED = "overlord.agent.selection_started"
    # When overlord begins agent selection process

    OVERLORD_AGENT_SELECTED = "overlord.agent.selected"
    # When overlord selects specific agent for task

    OVERLORD_TASK_DECOMPOSED = "overlord.task.decomposed"
    # When overlord breaks down complex task into subtasks

    OVERLORD_WORKFLOW_STARTED = "overlord.workflow.started"
    # When overlord starts workflow orchestration for a complex request

    OVERLORD_WORKFLOW_CANCELLED = "overlord.workflow.cancelled"
    # When a workflow is cancelled by user or system

    WORKFLOW_ANALYSIS_FAILED = "workflow.analysis.failed"
    # When workflow request analysis fails

    WORKFLOW_DECOMPOSITION_FAILED = "workflow.decomposition.failed"
    # When workflow task decomposition fails

    WORKFLOW_EXECUTION_FAILED = "workflow.execution.failed"
    # When workflow task execution fails

    WORKFLOW_DECOMPOSITION_COMPLETED = "workflow.decomposition.completed"
    # When workflow task decomposition completes successfully

    WORKFLOW_EXECUTION_STARTED = "workflow.execution.started"
    # When workflow execution starts

    WORKFLOW_EXECUTION_COMPLETED = "workflow.execution.completed"
    # When workflow execution completes successfully

    WORKFLOW_TASK_ASSIGNED = "workflow.task.assigned"
    # When a workflow task is assigned to an agent

    WORKFLOW_TASK_COMPLETED = "workflow.task.completed"
    # When a workflow task completes successfully

    WORKFLOW_APPROVAL_RECEIVED = "workflow.approval.received"
    # When user responds to workflow approval request

    # ===================================================================
    # SOP (Standard Operating Procedures) EVENTS
    # ===================================================================
    SOP_LOADED = "sop.loaded"
    # When SOPs are loaded at formation startup

    SOP_MATCHED = "sop.matched"
    # When an SOP is matched to a user request

    SOP_EXECUTED = "sop.executed"
    # When an SOP is used to generate a workflow

    SOP_NOT_FOUND = "sop.not_found"
    # When requested SOP is not found or disabled

    # ===================================================================
    # MEMORY & CONTEXT OPERATIONS
    # ===================================================================
    # Working memory operations
    MEMORY_WORKING_LOOKUP = "memory.working.lookup"
    # When searching working memory

    MEMORY_WORKING_RETRIEVED = "memory.working.retrieved"
    # When data is retrieved from working memory

    MEMORY_WORKING_UPDATED = "memory.working.updated"
    # When data is updated in working memory

    MEMORY_WORKING_UPDATE_FAILED = "memory.working.update_failed"
    # When working memory update fails

    MEMORY_WORKING_RETRIEVAL_FAILED = "memory.working.retrieval_failed"
    # When working memory retrieval fails

    MEMORY_AUTO_EXTRACTED = "memory.auto.extracted"
    # When memory is auto-extracted

    MEMORY_AUTO_EXTRACTION_FAILED = "memory.auto.extraction.failed"
    # When memory auto-extraction fails

    USER_INFO_EXTRACTION_STARTED = "user.info.extraction.started"
    # When background user information extraction task is initiated

    # Long-term memory operations
    MEMORY_LONG_TERM_LOOKUP = "memory.long_term.lookup"
    # When searching long-term memory

    MEMORY_LONG_TERM_RETRIEVED = "memory.long_term.retrieved"
    # When data is retrieved from long-term memory

    MEMORY_LONG_TERM_ENHANCED = "memory.long_term.enhanced"
    # When long-term memory is enhanced with new information

    MEMORY_LONG_TERM_UPDATED = "memory.long_term.updated"
    # When long-term memory is updated

    MEMORY_LONG_TERM_ENHANCEMENT_FAILED = "memory.long_term.enhancement_failed"
    # When long-term memory enhancement fails

    MEMORY_LONG_TERM_DELETION_FAILED = "memory.long_term.deletion_failed"
    # When long-term memory deletion fails

    MEMORY_LONG_TERM_UPDATE_FAILED = "memory.long_term.update_failed"
    # When long-term memory update fails

    MEMORY_LONG_TERM_RETRIEVAL_FAILED = "memory.long_term.retrieval_failed"
    # When long-term memory retrieval fails

    # ===================================================================
    # AGENT PROCESSING
    # ===================================================================
    AGENT_MESSAGE_PROCESSING = "agent.message.processing"
    # When agent begins processing a message

    AGENT_MESSAGE_COMPLETED = "agent.message.completed"
    # When agent completes message processing

    AGENT_MESSAGE_FAILED = "agent.message.failed"
    # When agent message processing fails

    AGENT_THINKING_STARTED = "agent.thinking.started"
    # When agent begins thinking/reasoning process

    AGENT_THINKING_COMPLETED = "agent.thinking.completed"
    # When agent completes thinking/reasoning

    AGENT_THINKING_FAILED = "agent.thinking.failed"
    # When agent thinking/reasoning fails

    AGENT_PLANNING_STARTED = "agent.planning.started"
    # When agent begins planning process

    AGENT_PLANNING_COMPLETED = "agent.planning.completed"
    # When agent completes planning

    AGENT_PLANNING_FAILED = "agent.planning.failed"
    # When agent planning fails

    AGENT_RESPONSE_GENERATED = "agent.response.generated"
    # When agent generates response

    AGENT_PLANNING = "agent.planning"
    # When agent creates execution plan

    # ===================================================================
    # PROMPT FORMATION & ENHANCEMENT
    # ===================================================================
    PROMPT_FORMATION_ENHANCEMENT_STARTED = "prompt.formation.enhancement.started"
    # When prompt formation enhancement begins

    PROMPT_FORMATION_ENHANCED = "prompt.formation.enhanced"
    # When prompt is enhanced with formation context

    PROMPT_VALIDATION_COMPLETED = "prompt.validation.completed"
    # When prompt validation completes

    # ===================================================================
    # EXCLUSION RULES GENERATION
    # ===================================================================
    EXCLUSION_RULES_GENERATION_STARTED = "exclusion_rules.generation.started"
    # When exclusion rules generation begins

    EXCLUSION_RULES_GENERATED = "exclusion_rules.generated"
    # When exclusion rules are generated

    AGENT_PROCESSING_ERROR = "agent.processing.error"
    # When agent encounters an error during processing

    # Tool chaining events
    AGENT_TOOL_CHAIN_ITERATION_STARTED = "agent.tool_chain.iteration_started"
    # When agent begins a tool chaining iteration

    AGENT_TOOL_CHAIN_ITERATION_COMPLETED = "agent.tool_chain.iteration_completed"
    # When agent completes a tool chaining iteration

    AGENT_TOOL_CHAIN_COMPLETED = "agent.tool_chain.completed"
    # When agent completes entire tool chaining sequence

    AGENT_TOOL_CHAIN_FAILED = "agent.tool_chain.failed"
    # When agent fails the entire tool chaining sequence

    # ===================================================================
    # MODEL OPERATIONS
    # ===================================================================
    MODEL_REQUEST_STARTED = "model.request.started"
    # When LLM request is initiated

    MODEL_REQUEST_COMPLETED = "model.request.completed"
    # When LLM request completes successfully

    MODEL_REQUEST_FAILED = "model.request.failed"
    # When LLM request fails

    MODEL_STREAMING_STARTED = "model.streaming.started"
    # When LLM streaming response begins

    MODEL_STREAMING_COMPLETED = "model.streaming.completed"
    # When LLM streaming response completes

    # ===================================================================
    # TOOL & MCP OPERATIONS
    # ===================================================================
    MCP_TOOL_DISCOVERY_STARTED = "mcp.tool.discovery_started"
    # When starting tool discovery for request

    MCP_TOOL_DISCOVERY_FAILED = "mcp.tool.discovery_failed"
    # When tool discovery fails for request

    MCP_TOOL_DISCOVERED = "mcp.tool.discovered"
    # When specific tool is discovered

    MCP_TOOL_CALLED = "mcp.tool.called"
    # When MCP tool is invoked

    MCP_TOOL_CALL_STARTED = "mcp.tool.call_started"
    # When MCP tool call begins

    MCP_TOOL_CALL_COMPLETED = "mcp.tool.call_completed"
    # When MCP tool call completes successfully

    MCP_TOOL_CALL_FAILED = "mcp.tool.call_failed"
    # When MCP tool call fails

    # ===================================================================
    # EXTERNAL AGENT COLLABORATION (A2A)
    # ===================================================================
    A2A_MESSAGE_SENT = "a2a.message.sent"
    # When A2A message is sent to external agent

    A2A_MESSAGE_RECEIVED = "a2a.message.received"
    # When A2A message is received from external agent

    A2A_MESSAGE_FAILED = "a2a.message.failed"
    # When A2A message delivery fails

    A2A_MESSAGE_PROCESSED = "a2a.message.processed"
    # When A2A message has been processed by receiving agent

    A2A_TASK_HANDOFF = "a2a.task.handoff"
    # When task is handed off from one agent to another via A2A

    AGENT_A2A = "agent.a2a"
    # General A2A-related agent event

    AGENT_A2A_MESSAGE_RECEIVED = "agent.a2a.message.received"
    # When agent receives an A2A message

    # Request/response flow
    A2A_REQUEST_SENT = "a2a.request.sent"  # outbound
    # When A2A request is sent to external agent

    A2A_REQUEST_RECEIVED = "a2a.request.received"  # inbound
    # When A2A request is received from external agent

    A2A_RESPONSE_SENT = "a2a.response.sent"  # outbound
    # When A2A response is sent to external agent

    A2A_RESPONSE_RECEIVED = "a2a.response.received"  # inbound
    # When A2A response is received from external agent

    # ===================================================================
    # INTERNAL AGENT COLLABORATION
    # ===================================================================
    COLAB_DISCOVERY_STARTED = "colab.discovery.started"
    # When internal agent discovery begins

    COLAB_REQUEST_SENT = "colab.request.sent"  # outbound
    # When request is sent to internal agent

    COLAB_REQUEST_RECEIVED = "colab.request.received"  # inbound
    # When request is received from internal agent

    COLAB_RESPONSE_SENT = "colab.response.sent"  # outbound
    # When response is sent to internal agent

    COLAB_RESPONSE_RECEIVED = "colab.response.received"  # inbound
    # When response is received from internal agent

    COLAB_MESSAGE_SENT = "colab.message.sent"
    # When message is sent to internal agent

    COLAB_MESSAGE_RECEIVED = "colab.message.received"
    # When message is received from internal agent

    # ===================================================================
    # RESPONSE GENERATION
    # ===================================================================
    RESPONSE_GENERATION_STARTED = "response.generation.started"
    # When response generation process begins

    RESPONSE_FORMATTED = "response.formatted"
    # When response is formatted for delivery

    RESPONSE_VALIDATION_COMPLETED = "response.validation.completed"
    # When response validation completes

    RESPONSE_CONVERSION_STARTED = "response.conversion.started"
    # When response format conversion begins

    RESPONSE_CONVERSION_COMPLETED = "response.conversion.completed"
    # When response format conversion completes

    RESPONSE_DELIVERY_STARTED = "response.delivery.started"
    # When response delivery begins

    RESPONSE_DELIVERY_FAILED = "response.delivery.failed"
    # When response delivery fails

    RESPONSE_DELIVERED = "response.delivered"
    # When response is successfully delivered

    RESPONSE_SYNTHESIZED = "response.synthesized"
    # When multiple responses are synthesized into final response

    # ===================================================================
    # ASYNC PROCESSING
    # ===================================================================
    ASYNC_THRESHOLD_DETECTED = "async.threshold.detected"
    # When request processing time exceeds async threshold

    ASYNC_PROCESSING_STARTED = "async.processing.started"
    # When request switches to async processing mode

    ASYNC_PROCESSING_COMPLETED = "async.processing.completed"
    # When async processing completes

    ASYNC_PROCESSING_FAILED = "async.processing.failed"
    # When async processing fails

    # ===================================================================
    # WEBHOOK DELIVERY
    # ===================================================================
    WEBHOOK_DELIVERY_STARTED = "webhook.delivery.started"
    # When webhook delivery attempt begins

    WEBHOOK_SENT = "webhook.sent"
    # When webhook notification is sent

    WEBHOOK_FAILED = "webhook.failed"
    # When webhook delivery fails

    # ===================================================================
    # CLARIFICATION HANDLING
    # ===================================================================
    CLARIFICATION_REQUEST_SENT = "clarification.request.sent"
    # When clarification request is sent to user

    CLARIFICATION_FAILED = "clarification.failed"
    # When clarification fails

    CLARIFICATION_RESPONSE_RECEIVED = "clarification.response.received"
    # When clarification response is received from user

    CLARIFICATION_COMPLETED = "clarification.completed"
    # When clarification completes

    CLARIFICATION_REQUEST_GENERATED = "clarification.request.generated"
    # When clarification request is generated for user

    CLARIFICATION_SKIPPED = "clarification.skipped"
    # When clarification is skipped (disabled or not needed)

    # ===================================================================
    # CREDENTIAL HANDLING
    # ===================================================================
    CREDENTIAL_PROVIDED = "credential.provided"
    # When user provides credentials via clarification or direct input

    # ===================================================================
    # REQUEST ANALYSIS & CLASSIFICATION
    # ===================================================================
    REQUEST_TOPICS_EXTRACTED = "request.topics.extracted"
    # When topic tags are dynamically extracted from user request via LLM analysis

    # ===================================================================
    # SCHEDULER OPERATIONS
    # ===================================================================
    SCHEDULER_JOB_REQUESTED = "scheduler.job.requested"
    # When user requests to create a scheduled job

    SCHEDULED_JOB_CREATED = "scheduled.job.created"
    # When a scheduled job is created

    SCHEDULED_JOB_EXECUTED = "scheduled.job.executed"
    # When a scheduled job is executed

    SCHEDULED_JOB_COMPLETED = "scheduled.job.completed"
    # When a one-time scheduled job is completed

    SCHEDULED_JOB_FAILED = "scheduled.job.failed"
    # When a scheduled job execution fails

    SCHEDULED_JOB_EXECUTION_TRACKED = "scheduled.job.execution.tracked"
    # When a scheduled job execution is tracked

    SCHEDULED_JOBS_FOUND = "scheduled.jobs.found"
    # When scheduled jobs are found due for execution

    SCHEDULED_JOB_EXCLUDED = "scheduled.job.excluded"
    # When a scheduled job is excluded from execution

    SCHEDULED_JOB_STARTED = "scheduled.job.started"
    # When a scheduled job execution starts

    ONETIME_JOB_COMPLETED = "scheduled.onetime.completed"
    # When a one-time job completes and is marked done

    SCHEDULED_JOB_PAUSED = "scheduled.job.paused"
    # When a scheduled job is paused

    SCHEDULED_JOB_RESUMED = "scheduled.job.resumed"
    # When a scheduled job is resumed

    SCHEDULED_JOB_UPDATED = "scheduled.job.updated"
    # When a scheduled job configuration is updated

    SCHEDULED_JOB_DELETED = "scheduled.job.deleted"
    # When a scheduled job is deleted

    ONETIME_JOB_MARKED_COMPLETED = "onetime.job.marked.completed"
    # When a one-time job is marked as completed

    SCHEDULED_JOB_ASYNC_INITIATED = "scheduled.job.async.initiated"
    # When async execution is initiated for a scheduled job

    SCHEDULED_JOB_WEBHOOK_RECEIVED = "scheduled.job.webhook.received"
    # When webhook response is received for a scheduled job


class ServerEvents(Enum):
    """Server event types for MUXI observability"""

    SERVER_STARTED = "server.started"
    # When server starts

    SERVER_FAILED = "server.failed"
    # When server fails

    SERVER_INITIALIZING = "server.initializing"
    # When server initialization begins

    SERVER_STARTING = "server.starting"
    # When server is starting up

    SERVER_RESTARTING = "server.restarting"
    # When server is restarting (replacing stopped instance)

    OVERLORD_STARTING = "server.overlord.starting"
    # When overlord is starting for the server

    API_KEYS_LOADED = "server.api_keys.loaded"
    # When API keys are loaded from configuration

    REQUEST_RECEIVED = "server.request.received"
    # When server receives an HTTP request

    REQUEST_COMPLETED = "server.request.completed"
    # When server completes processing an HTTP request


class APIEvents(Enum):
    """API-specific event types for Formation API observability"""

    API_REQUEST = "api.request"
    # API request with auth and metadata details

    API_RESPONSE = "api.response"
    # API response with status and timing


class ErrorEvents(Enum):
    """Error event types for MUXI observability (routed to stderr)."""

    # ===================================================================
    # VALIDATION ERRORS
    # ===================================================================
    VALIDATION_FAILED = "error.validation.failed"
    # When input validation fails (malformed data, missing fields, etc.)

    SCHEMA_VALIDATION_FAILED = "error.schema.validation.failed"
    # When data doesn't match expected schema

    # ===================================================================
    # AUTHENTICATION & AUTHORIZATION ERRORS
    # ===================================================================
    AUTHENTICATION_FAILED = "error.authentication.failed"
    # When user authentication fails

    AUTHORIZATION_FAILED = "error.authorization.failed"
    # When user lacks permission for requested action

    TOKEN_EXPIRED = "error.token.expired"
    # When authentication token has expired

    TOKEN_INVALID = "error.token.invalid"
    # When authentication token is malformed or invalid

    # ===================================================================
    # NETWORK & CONNECTIVITY ERRORS
    # ===================================================================
    NETWORK_ERROR = "error.network.error"
    # When network connectivity issues occur

    CONNECTION_TIMEOUT = "error.connection.timeout"
    # When connection times out

    CONNECTION_REFUSED = "error.connection.refused"
    # When connection is refused by target

    # ===================================================================
    # RESOURCE ERRORS
    # ===================================================================
    RESOURCE_NOT_FOUND = "error.resource.not_found"
    # When requested resource doesn't exist

    RESOURCE_UNAVAILABLE = "error.resource.unavailable"
    # When resource exists but is temporarily unavailable

    RESOURCE_EXHAUSTED = "error.resource.exhausted"
    # When system resources are exhausted (memory, disk, etc.)

    # ===================================================================
    # RATE LIMITING ERRORS
    # ===================================================================
    RATE_LIMIT_EXCEEDED = "error.rate_limit.exceeded"
    # When request rate exceeds configured limits

    QUOTA_EXCEEDED = "error.quota.exceeded"
    # When usage quota is exceeded

    # ===================================================================
    # CONFIGURATION ERRORS
    # ===================================================================
    CONFIGURATION_ERROR = "error.configuration.error"
    # When system configuration is invalid or missing

    ENVIRONMENT_ERROR = "error.environment.error"
    # When required environment variables are missing or invalid

    # ===================================================================
    # SYSTEM ERRORS
    # ===================================================================
    INTERNAL_ERROR = "error.internal.error"
    # When unexpected internal system error occurs

    GENERIC_ERROR = "error.generic"
    # Generic error for uncategorized failures

    PROCESSING_ERROR = "error.processing"
    # When general processing operation fails

    OVERLORD_PROCESSING_ERROR = "error.overlord.processing"
    # When overlord encounters processing error

    SERVICE_UNAVAILABLE = "error.service.unavailable"
    # When required service is unavailable

    DEPENDENCY_ERROR = "error.dependency.error"
    # When external dependency fails or is unavailable

    # ===================================================================
    # LLM & AI SERVICE ERRORS
    # ===================================================================
    LLM_INITIALIZATION_FAILED = "error.llm.initialization.failed"
    # When LLM service initialization fails

    # ===================================================================
    # DATABASE ERRORS
    # ===================================================================
    DATABASE_EXTENSION_FAILED = "error.database.extension.failed"
    # When database extension loading fails

    DATABASE_TABLE_CREATION_FAILED = "error.database.table.creation.failed"
    # When database table creation fails

    DATABASE_OPERATION_FAILED = "error.database.operation.failed"
    # When a database operation fails

    # ===================================================================
    # DATA ERRORS
    # ===================================================================
    DATA_CORRUPTION = "error.data.corruption"
    # When data corruption is detected

    SERIALIZATION_ERROR = "error.serialization.error"
    # When data serialization/deserialization fails

    ENCODING_ERROR = "error.encoding.error"
    # When character encoding/decoding fails

    # ===================================================================
    # FEATURE-SPECIFIC ERRORS (Knowledge, Memory, Artifacts, etc.)
    # ===================================================================
    KNOWLEDGE_SOURCE_MISSING = "error.knowledge.source.missing"
    # When knowledge source file or directory doesn't exist

    MARKITDOWN_INITIALIZATION_FAILED = "error.markitdown.initialization.failed"
    # When MarkItDown document processor initialization fails

    MEMORY_RETRIEVAL_FAILED = "error.memory.retrieval.failed"
    # When memory system retrieval operation fails

    MEMORY_CLEAR_FAILED = "error.memory.clear.failed"
    # When memory system clear operation fails

    JSON_PARSE_FAILED = "error.json.parse.failed"
    # When JSON parsing fails

    ARTIFACT_FIELD_MISSING = "error.artifact.field.missing"
    # When required artifact field is missing

    THUMBNAIL_GENERATION_FAILED = "error.thumbnail.generation.failed"
    # When document thumbnail generation fails

    PERSONA_FILE_MISSING = "error.persona.file.missing"
    # When agent persona configuration file is missing

    SECRET_INTERPOLATION_FAILED = "error.secret.interpolation.failed"
    # When secret value interpolation in configuration fails

    SOP_INITIALIZATION_FAILED = "error.sop.initialization.failed"
    # When SOP (Standard Operating Procedure) system initialization fails

    KNOWLEDGE_SEARCH_FAILED = "error.knowledge.search.failed"
    # When knowledge base search operation fails

    EMBEDDINGS_GENERATION_FAILED = "error.embeddings.generation.failed"
    # When embedding generation for text fails

    # ===================================================================
    # AGENT LIFECYCLE ERRORS
    # ===================================================================
    AGENT_CREATION_FAILED = "error.agent.creation.failed"
    # When dynamic agent creation via API fails

    AGENT_REGISTRATION_FAILED = "error.agent.registration.failed"
    # When agent capability registration fails

    AGENT_FAILED = "error.agent.failed"
    # When agent loading or initialization fails

    # ===================================================================
    # A2A (AGENT-TO-AGENT) ERRORS
    # ===================================================================
    A2A_AGENT_REGISTRATION_FAILED = "error.a2a.agent.registration.failed"
    # When A2A external registry registration fails

    A2A_MESSAGE_HANDLING_FAILED = "error.a2a.message.handling.failed"
    # When Agent-to-Agent message handling fails

    MEMORY_OPERATION_FAILED = "error.memory.operation.failed"
    # When general memory system operation fails

    MEMORY_INITIALIZATION_FAILED = "error.memory.initialization.failed"
    # When memory system initialization fails

    FORMATION_INITIALIZATION_FAILED = "error.formation.initialization.failed"
    # When formation initialization fails

    PLANNING_TEMPLATE_MISSING = "error.planning.template.missing"
    # When agent planning template file is missing

    PARAMETER_VALIDATION_FAILED = "error.parameter.validation.failed"
    # When parameter validation fails

    METADATA_PERSISTENCE_FAILED = "error.metadata.persistence.failed"
    # When metadata persistence to storage fails

    REFERENCE_PERSISTENCE_FAILED = "error.reference.persistence.failed"
    # When reference data persistence to storage fails

    RETRY_ATTEMPTED = "error.retry.attempted"
    # When a retry is attempted

    WARNING = "error.warning"
    # When we want to warn about something

    # ===================================================================
    # RESILIENCE ERRORS
    # ===================================================================
    CIRCUIT_BREAKER_FALLBACK_FAILED = "error.circuit_breaker.fallback.failed"
    # When circuit breaker fallback execution fails

    FALLBACK_EXECUTION_FAILED = "error.fallback.execution.failed"
    # When fallback function execution fails

    RECOVERY_STRATEGY_FAILED = "error.recovery.strategy.failed"
    # When recovery strategy execution fails

    # ===================================================================
    # MCP ERRORS
    # ===================================================================
    TOOL_CALL_ERROR = "error.mcp.tool.call.failed"
    # When MCP tool execution fails after retries

    TOOL_PARSE_ERROR = "error.mcp.tool.parse.failed"
    # When parsing tool calls from LLM response fails

    RETRY_FAILED = "error.retry.failed"
    # When operation fails after all retry attempts exhausted


@dataclass
class TokenUsage:
    """Enhanced token usage tracking with cache support using self-documenting arrays."""

    # Field definitions (class constant for self-documentation)
    FIELDS = ["total", "input", "output", "total_cached", "input_cached", "output_cached"]

    # Internal storage as arrays matching FIELDS order
    total: List[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])
    breakdown: Dict[str, List[int]] = field(default_factory=dict)

    def add_tokens(self, model: str, usage_data: Dict[str, int]) -> None:
        """Add comprehensive token usage data in array format."""
        # Extract values in FIELDS order
        values = [
            usage_data.get('total_tokens', 0),
            usage_data.get('prompt_tokens', 0),
            usage_data.get('completion_tokens', 0),
            usage_data.get('prompt_tokens_cached', 0) + usage_data.get('completion_tokens_cached', 0),  # total_cached
            usage_data.get('prompt_tokens_cached', 0),
            usage_data.get('completion_tokens_cached', 0)
        ]

        # Update totals (element-wise addition)
        for i, value in enumerate(values):
            self.total[i] += value

        # Update model breakdown
        if model not in self.breakdown:
            self.breakdown[model] = [0, 0, 0, 0, 0, 0]

        for i, value in enumerate(values):
            self.breakdown[model][i] += value

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to self-documenting observability log format."""
        return {
            "fields": self.FIELDS,
            "total": self.total,
            "breakdown": self.breakdown
        }

    # Backward compatibility methods
    @property
    def total_tokens(self) -> int:
        """Backward compatibility: get total tokens."""
        return self.total[0]

    @property
    def breakdown_legacy(self) -> Dict[str, int]:
        """Backward compatibility: get breakdown as model -> total_tokens dict."""
        return {model: tokens[0] for model, tokens in self.breakdown.items()}


@dataclass
class RequestContext:
    """Request context tracking for complete lifecycle."""

    id: str
    status: str = "processing"
    started: float = field(default_factory=lambda: time.time() * 1000)  # milliseconds
    formation_id: Optional[str] = None

    # User identity (three aspects for multi-identity support)
    internal_user_id: Optional[int] = None      # Database ID (for queries) - NEVER exposed externally
    muxi_user_id: Optional[str] = None          # MUXI's canonical public_id (e.g., "usr_abc123") for observability
    user_id: Optional[str] = None               # What developer provided (e.g., "alice@email.com") - channel context

    session_id: Optional[str] = None
    tokens: TokenUsage = field(default_factory=TokenUsage)
    _parent_events: Set[str] = field(default_factory=set, init=False)

    @property
    def duration_ms(self) -> int:
        """Calculate duration in milliseconds since request start."""
        return int(time.time() * 1000 - self.started)

    def add_parent_event(self, event_id: str) -> None:
        """Track parent event relationships."""
        self._parent_events.add(event_id)

    def complete(self) -> None:
        """Mark request as completed."""
        self.status = "completed"

    def fail(self) -> None:
        """Mark request as failed."""
        self.status = "failed"


@dataclass
class InitFailureInfo:
    """Structured error information for initialization failures.

    Provides operational guidance instead of raw stack traces for better
    debugging experience during formation startup.
    """

    component: str
    """Component that failed (e.g., 'MCP server: filesystem')"""

    problem: str
    """Plain English summary of what went wrong"""

    context: str
    """Where in formation config (e.g., 'formation.afs:45 (mcp.servers.filesystem)')"""

    causes: list[str]
    """List of likely reasons for the failure"""

    fixes: list[str]
    """Actionable steps to resolve the issue"""

    technical: str
    """Original exception with full traceback for debugging"""


class InitEventFormatter:
    """Linux systemd-style formatter for initialization events.

    Provides clean, consistent startup output with clear status indicators:
    - [  OK  ] for successful initialization
    - [ WARN ] for warnings (non-blocking issues)
    - [ FAIL ] for failures (blocking issues that require intervention)
    - [ INFO ] for informational messages

    Design principles:
    - One line per distributed service (MCP, A2A, database)
    - Use formation IDs/names, not full URLs/connection strings
    - Fail-fast with structured error details
    - Show full technical details by default (init failures happen at dev/deployment time)
    - Auto-detects color support (TTY, TERM, NO_COLOR env vars)
    """

    @staticmethod
    def _supports_color() -> bool:
        """
        Detect if the terminal supports ANSI colors.

        Checks multiple indicators:
        - NO_COLOR env var (standard: https://no-color.org/)
        - FORCE_COLOR env var (override for CI/testing)
        - stdout is a TTY
        - TERM env var indicates color support
        - Not in dumb terminal

        Returns:
            True if colors should be used, False otherwise
        """
        import sys
        import os

        # Respect NO_COLOR standard (https://no-color.org/)
        if os.environ.get('NO_COLOR'):
            return False

        # Allow forcing colors (useful for CI/testing)
        if os.environ.get('FORCE_COLOR'):
            return True

        # Check if stdout is a TTY
        if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
            return False

        # Check TERM environment variable
        term = os.environ.get('TERM', '').lower()
        if term == 'dumb':
            return False
        if 'color' in term or 'ansi' in term or 'xterm' in term:
            return True

        # Default to True if stdout is a TTY
        return True

    @staticmethod
    def _c(code: str) -> str:
        """Get ANSI color code if supported, empty string otherwise."""
        return code if InitEventFormatter._supports_color() else ""

    @staticmethod
    def format_ok(message: str, details: Optional[str] = None) -> str:
        """Format successful initialization event.

        Args:
            message: Main success message (e.g., 'MCP server: filesystem')
            details: Optional details to append (e.g., '3 tools')

        Returns:
            Formatted line: '[  OK  ] MCP server: filesystem (3 tools)'
        """
        green = InitEventFormatter._c("\033[92m")
        reset = InitEventFormatter._c("\033[0m")
        status = f"{green}[  OK  ]{reset}"
        if details:
            return f"{status} {message} ({details})"
        return f"{status} {message}"

    @staticmethod
    def format_warn(message: str, details: Optional[str] = None) -> str:
        """Format warning event (non-blocking issue).

        Args:
            message: Main warning message (e.g., 'Vector memory: disabled')
            details: Optional details to append

        Returns:
            Formatted line: '[ WARN ] Vector memory: disabled'
        """
        yellow = InitEventFormatter._c("\033[93m")
        reset = InitEventFormatter._c("\033[0m")
        status = f"{yellow}[ WARN ]{reset}"
        if details:
            return f"{status} {message} ({details})"
        return f"{status} {message}"

    @staticmethod
    def format_info(message: str, details: Optional[str] = None) -> str:
        """Format informational event.

        Args:
            message: Main info message (e.g., 'Buffer memory: FIFO mode')
            details: Optional details to append (e.g., '100 messages')

        Returns:
            Formatted line: '[ INFO ] Buffer memory: FIFO mode (100 messages)'
        """
        blue = InitEventFormatter._c("\033[94m")
        reset = InitEventFormatter._c("\033[0m")
        status = f"{blue}[ INFO ]{reset}"
        if details:
            return f"{status} {message} ({details})"
        return f"{status} {message}"

    @staticmethod
    def format_fail(failure_info: InitFailureInfo) -> str:
        """Format failure event with structured error details.

        Args:
            failure_info: Structured failure information

        Returns:
            Multi-line formatted error with operational guidance and technical details

        Example output:
            [ FAIL ] MCP server: filesystem

              Connection timeout after 5 seconds

              The server didn't respond during startup. Common causes:
                • Server executable not installed or not in PATH
                • Incorrect command in formation config
                • Server crashed on launch

              To fix:
                1. Test manually: npx @modelcontextprotocol/server-filesystem
                2. Install if needed: npm install -g @modelcontextprotocol/server-filesystem
                3. Check formation.afs → mcp.servers.filesystem.command

              Config: formation.afs:45 (mcp.servers.filesystem)

              Traceback (most recent call last):
                File "src/muxi/services/mcp/registry.py", line 156, in register_server
                  response = await client.connect(timeout=5.0)
              TimeoutError: Server did not respond within 5 seconds
        """
        red = InitEventFormatter._c("\033[91m")
        reset = InitEventFormatter._c("\033[0m")
        status = f"{red}[ FAIL ]{reset}"

        lines = [
            f"{status} {failure_info.component}",
            "",
            f"  {failure_info.problem}",
            "",
        ]

        # Add causes if provided
        if failure_info.causes:
            lines.append("  Common causes:")
            for cause in failure_info.causes:
                lines.append(f"    • {cause}")
            lines.append("")

        # Add fixes if provided
        if failure_info.fixes:
            lines.append("  To fix:")
            for i, fix in enumerate(failure_info.fixes, 1):
                lines.append(f"    {i}. {fix}")
            lines.append("")

        # Add config location
        lines.append(f"  Config: {failure_info.context}")
        lines.append("")

        # Add technical details (indented for readability)
        if failure_info.technical:
            technical_lines = failure_info.technical.split("\n")
            for line in technical_lines:
                lines.append(f"  {line}")

        return "\n".join(lines)

    @staticmethod
    def format_summary(duration_s: float, service_count: int, warning_count: int, error_count: int) -> str:
        """Format startup summary line.

        Args:
            duration_s: Total startup duration in seconds
            service_count: Number of services initialized
            warning_count: Number of warnings encountered
            error_count: Number of errors encountered

        Returns:
            Summary line: 'Startup completed in 2.3s (8 services, 1 warning, 0 errors)'
        """
        summary = f"Startup completed in {duration_s:.1f}s ({service_count} services"

        if warning_count > 0:
            summary += f", {warning_count} warning{'s' if warning_count != 1 else ''}"
        else:
            summary += ", 0 warnings"

        if error_count > 0:
            summary += f", {error_count} error{'s' if error_count != 1 else ''}"
        else:
            summary += ", 0 errors"

        summary += ")"
        return summary
