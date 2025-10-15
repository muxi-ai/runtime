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

    INITIALIZING = "service.initializing"
    # When server starts initializing

    SERVICE_STARTED = "service.started"
    # When server is fully initialized and ready

    CLEANUP = "cleanup"
    # When server is cleaning up

    OVERLORD_SHUTDOWN = "overlord.shutdown"
    # When overlord is shutting down gracefully

    # ===================================================================
    # MCP SYSTEM EVENTS
    # ===================================================================
    MCP_SERVER_PROCESS_STARTED = "mcp.server.process.started"
    # When MCP server subprocess is launched

    MCP_SERVER_PROCESS_FAILED = "mcp.server.process.failed"
    # When MCP server subprocess fails to start or crashes

    MCP_SERVER_REGISTERED = "mcp.server.registration.completed"
    # When MCP server is successfully registered

    MCP_SERVER_REGISTRATION_FAILED = "mcp.server.registration.failed"
    # When MCP server registration fails

    MCP_SERVER_REGISTRATION_STARTED = "mcp.server.registration.started"
    # When MCP server registration begins

    MCP_SERVER_REGISTRATION_COMPLETED = "mcp.server.registration.completed"
    # When MCP server registration completes successfully

    MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery.completed"
    # When MCP server tool discovery finishes

    # Connection lifecycle events
    MCP_SERVER_CONNECTING = "mcp.server.connecting"
    # When starting connection to MCP server

    MCP_SERVER_CONNECTED = "mcp.server.connected"
    # When MCP server connection is established

    MCP_SERVER_CONNECTION_FAILED = "mcp.server.connection_failed"
    # When MCP server connection fails

    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
    # When MCP server disconnects

    MCP_SERVER_DISCONNECTION_FAILED = "mcp.server.disconnection_failed"
    # When MCP server disconnection fails

    MCP_SERVER_RECONNECTING = "mcp.server.reconnecting"
    # When attempting to reconnect to MCP server

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

    # ===================================================================
    # MCP TRANSPORT EVENTS (Added for Streamable HTTP implementation)
    # ===================================================================
    MCP_TRANSPORT_DETECTED = "mcp.transport.detected"
    # When transport type is auto-detected for MCP server

    MCP_TRANSPORT_DETECTION_FAILED = "mcp.transport.detection.failed"
    # When transport auto-detection fails

    MCP_TRANSPORT_ATTEMPT = "mcp.transport.attempt"
    # When attempting to connect with specific transport type

    MCP_TRANSPORT_FAILED = "mcp.transport.failed"
    # When specific transport connection fails

    MCP_TRANSPORT_FALLBACK_SUCCESS = "mcp.transport.fallback.success"
    # When fallback transport succeeds after primary fails

    # ===================================================================
    # AGENT SYSTEM EVENTS
    # ===================================================================
    AGENT_INITIALIZED = "agent.initialized"
    # When agent instance is created and configured

    # ===================================================================
    # A2A SYSTEM EVENTS
    # ===================================================================
    A2A_CONFIG_LOAD_STARTED = "a2a.config.load.started"
    # When starting to load A2A configuration

    A2A_CONFIG_LOAD_COMPLETED = "a2a.config.load.completed"
    # When A2A configuration is successfully loaded

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

    A2A_SERVER_STARTED = "a2a.server.started"
    # When A2A server component starts

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

    OVERLORD_INITIALIZING = "overlord.initializing"
    # When overlord component starts initialization

    OVERLORD_STARTED = "overlord.started"
    # When overlord component is fully initialized and ready

    CACHE_MANAGER_STARTED = "cache.manager.started"
    # When cache management system starts

    MEMORY_OPTIMIZER_STARTED = "memory.optimizer.started"
    # When memory optimization system starts

    # ===================================================================
    # AUTHENTICATION & SECURITY EVENTS
    # ===================================================================
    AUTH_MANAGER_INITIALIZED = "auth.manager.initialized"
    # When authentication manager is initialized

    INBOUND_AUTH_INITIALIZED = "inbound.auth.initialized"
    # When inbound authentication system is initialized

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
    # DATABASE/STORAGE OPERATIONS
    # ===================================================================
    DB_CONNECTION_STARTED = "db.connection.started"
    # When database connection is initiated

    DB_CONNECTION_FAILED = "db.connection.failed"
    # When database connection fails

    # ===================================================================
    # SCHEDULER SYSTEM OPERATIONS
    # ===================================================================
    SCHEDULER_SERVICE_INITIALIZED = "scheduler.service.initialized"
    # When scheduler service is initialized

    SCHEDULER_MANAGER_INITIALIZED = "scheduler.manager.initialized"
    # When scheduler job manager is initialized

    SCHEDULER_PARSER_INITIALIZED = "scheduler.parser.initialized"
    # When scheduler parser is initialized

    SCHEDULER_DATABASE_INITIALIZED = "scheduler.database.initialized"
    # When scheduler database is initialized

    DATABASE_MANAGER_INITIALIZED = "database.manager.initialized"
    # When database manager is initialized

    DATABASE_TABLES_CREATED = "database.tables.created"
    # When database tables are created

    # ===================================================================
    # NETWORK/COMMUNICATION INFRASTRUCTURE
    # ===================================================================
    NETWORK_INTERFACE_INITIALIZED = "network.interface.initialized"
    # When network interface is initialized

    NETWORK_INTERFACE_FAILED = "network.interface.failed"
    # When network interface initialization fails


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

    # ===================================================================
    # SOP (Standard Operating Procedures) EVENTS
    # ===================================================================
    SOP_LOADED = "sop.loaded"
    # When SOPs are loaded at formation startup

    SOP_MATCHED = "sop.matched"
    # When an SOP is matched to a user request

    SOP_EXECUTED = "sop.executed"
    # When an SOP is used to generate a workflow

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

    # ===================================================================
    # REQUEST ANALYSIS & CLASSIFICATION
    # ===================================================================
    REQUEST_TOPICS_EXTRACTED = "request.topics.extracted"
    # When topic tags are dynamically extracted from user request via LLM analysis

    # ===================================================================
    # SCHEDULER OPERATIONS
    # ===================================================================
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

    RETRY_ATTEMPTED = "error.retry.attempted"
    # When a retry is attempted

    WARNING = "error.warning"
    # When we want to warn about something


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
    """Where in formation config (e.g., 'formation.yaml:45 (mcp.servers.filesystem)')"""
    
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
    """
    
    # ANSI color codes
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    @staticmethod
    def format_ok(message: str, details: Optional[str] = None) -> str:
        """Format successful initialization event.
        
        Args:
            message: Main success message (e.g., 'MCP server: filesystem')
            details: Optional details to append (e.g., '3 tools')
        
        Returns:
            Formatted line: '[  OK  ] MCP server: filesystem (3 tools)'
        """
        status = f"{InitEventFormatter.GREEN}[  OK  ]{InitEventFormatter.RESET}"
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
        status = f"{InitEventFormatter.YELLOW}[ WARN ]{InitEventFormatter.RESET}"
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
        status = f"{InitEventFormatter.BLUE}[ INFO ]{InitEventFormatter.RESET}"
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
                3. Check formation.yaml → mcp.servers.filesystem.command
              
              Config: formation.yaml:45 (mcp.servers.filesystem)
              
              Traceback (most recent call last):
                File "src/muxi/services/mcp/registry.py", line 156, in register_server
                  response = await client.connect(timeout=5.0)
              TimeoutError: Server did not respond within 5 seconds
        """
        status = f"{InitEventFormatter.RED}[ FAIL ]{InitEventFormatter.RESET}"
        
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
