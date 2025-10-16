#!/usr/bin/env python3
"""
Analyze missing events and provide recommendations.
Either suggest existing alternative or mark for re-addition.
"""

import csv
from collections import defaultdict
from pathlib import Path


# Map of missing events to recommendations
RECOMMENDATIONS = {
    # ============================================================================
    # INIT PHASE EVENTS - REMOVE (replaced by InitEventFormatter)
    # ============================================================================
    'AGENT_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter print statements',
        'alternative': 'Remove observability.observe() call - agent loading shown in init output'
    },
    'SERVICE_STARTED': {
        'action': 'REMOVE_OR_REPLACE',
        'reason': 'Context-dependent: init phase = remove, runtime = use OPERATION_COMPLETED',
        'alternative': 'If init: remove. If runtime: use SystemEvents.OPERATION_COMPLETED'
    },
    'SERVICE_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove observability.observe() call'
    },
    'A2A_SERVER_STARTED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - A2A server start shown in init output'
    },
    'MCP_SERVER_REGISTRATION_STARTED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - MCP registration shown in init output'
    },
    'MCP_SERVER_REGISTRATION_COMPLETED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - MCP registration shown in init output'
    },
    'MCP_SERVER_CONNECTED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - MCP connection shown in init output'
    },
    'MCP_SERVER_CONNECTING': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - too granular'
    },
    'DATABASE_TABLES_CREATED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - database schema shown in init output'
    },
    'DATABASE_MANAGER_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - database initialization shown in init output'
    },
    'SCHEDULER_PARSER_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove - internal initialization detail'
    },
    'SCHEDULER_MANAGER_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove - internal initialization detail'
    },
    'SCHEDULER_SERVICE_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - replaced by InitEventFormatter',
        'alternative': 'Remove - scheduler shown in init output'
    },
    'MCP_TOOL_DISCOVERY_COMPLETED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - tool count shown in MCP init message',
        'alternative': 'Remove - included in InitEventFormatter MCP output'
    },
    'MCP_TRANSPORT_DETECTED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - transport shown in MCP init message',
        'alternative': 'Remove - included in InitEventFormatter MCP output'
    },
    'A2A_CONFIG_LOAD_STARTED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'A2A_CONFIG_LOAD_COMPLETED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'A2A_AUTH_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'A2A_REGISTRY_CLIENT_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'A2A_CARD_GENERATOR_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'A2A_DISCOVERY_INITIALIZED': {
        'action': 'REMOVE',
        'reason': 'Init phase event - too granular',
        'alternative': 'Remove'
    },
    'SERVER_STARTED': {
        'action': 'USE_EXISTING',
        'reason': 'Event exists in ServerEvents enum',
        'alternative': 'Use ServerEvents.SERVER_STARTED (already exists)'
    },
    
    # ============================================================================
    # A2A RUNTIME EVENTS - ADD BACK TO ENUM
    # ============================================================================
    'A2A_CREDENTIAL_LOADED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event for A2A credential management',
        'alternative': 'Add to SystemEvents: A2A_CREDENTIAL_LOADED = "a2a.credential.loaded"'
    },
    'A2A_AUTH_VALIDATION_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A auth validation failure',
        'alternative': 'Add to SystemEvents: A2A_AUTH_VALIDATION_FAILED = "a2a.auth.validation_failed"'
    },
    'A2A_AUTH_VALIDATED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A auth validation success',
        'alternative': 'Add to SystemEvents: A2A_AUTH_VALIDATED = "a2a.auth.validated"'
    },
    'A2A_AUTH_VALIDATING': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A auth validation in progress',
        'alternative': 'Add to SystemEvents: A2A_AUTH_VALIDATING = "a2a.auth.validating"'
    },
    'A2A_DISCOVERY_COMPLETED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent discovery completed',
        'alternative': 'Add to SystemEvents: A2A_DISCOVERY_COMPLETED = "a2a.discovery.completed"'
    },
    'A2A_DISCOVERY_STARTED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent discovery started',
        'alternative': 'Add to SystemEvents: A2A_DISCOVERY_STARTED = "a2a.discovery.started"'
    },
    'A2A_DISCOVERY_STOPPED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent discovery stopped',
        'alternative': 'Add to SystemEvents: A2A_DISCOVERY_STOPPED = "a2a.discovery.stopped"'
    },
    'A2A_DISCOVERY_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent discovery failed',
        'alternative': 'Add to SystemEvents: A2A_DISCOVERY_FAILED = "a2a.discovery.failed"'
    },
    'A2A_MESSAGE_SENT': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A message sent',
        'alternative': 'Add to SystemEvents: A2A_MESSAGE_SENT = "a2a.message.sent"'
    },
    'A2A_MESSAGE_RECEIVED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A message received',
        'alternative': 'Add to SystemEvents: A2A_MESSAGE_RECEIVED = "a2a.message.received"'
    },
    'A2A_MESSAGE_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A message failed',
        'alternative': 'Add to SystemEvents: A2A_MESSAGE_FAILED = "a2a.message.failed"'
    },
    'A2A_MESSAGE_HANDLING_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A message handling failed',
        'alternative': 'Add to ErrorEvents: A2A_MESSAGE_HANDLING_FAILED = "error.a2a.message.handling.failed"'
    },
    'A2A_AGENT_REGISTERED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - external agent registered',
        'alternative': 'Add to SystemEvents: A2A_AGENT_REGISTERED = "a2a.agent.registered"'
    },
    'A2A_AGENT_DEREGISTERED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - external agent deregistered',
        'alternative': 'Add to SystemEvents: A2A_AGENT_DEREGISTERED = "a2a.agent.deregistered"'
    },
    'A2A_REGISTERED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - registered with A2A registry',
        'alternative': 'Add to SystemEvents: A2A_REGISTERED = "a2a.registration.completed"'
    },
    'A2A_REGISTRATION_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A registration failed',
        'alternative': 'Add to SystemEvents: A2A_REGISTRATION_FAILED = "a2a.registration.failed"'
    },
    'A2A_DEREGISTERED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - deregistered from A2A registry',
        'alternative': 'Add to SystemEvents: A2A_DEREGISTERED = "a2a.deregistration.completed"'
    },
    'A2A_DEREGISTRATION_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A deregistration failed',
        'alternative': 'Add to SystemEvents: A2A_DEREGISTRATION_FAILED = "a2a.deregistration.failed"'
    },
    'A2A_REGISTRY_CONNECTED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - connected to A2A registry',
        'alternative': 'Add to SystemEvents: A2A_REGISTRY_CONNECTED = "a2a.registry.connected"'
    },
    'A2A_REGISTRY_DISCONNECTED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - disconnected from A2A registry',
        'alternative': 'Add to SystemEvents: A2A_REGISTRY_DISCONNECTED = "a2a.registry.disconnected"'
    },
    'A2A_HEALTH_CHECK_STARTED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A health check started',
        'alternative': 'Add to SystemEvents: A2A_HEALTH_CHECK_STARTED = "a2a.health.check.started"'
    },
    'A2A_HEALTH_CHECK_COMPLETED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A health check completed',
        'alternative': 'Add to SystemEvents: A2A_HEALTH_CHECK_COMPLETED = "a2a.health.check.completed"'
    },
    'A2A_HEALTH_CHECK_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A health check failed',
        'alternative': 'Add to SystemEvents: A2A_HEALTH_CHECK_FAILED = "a2a.health.check.failed"'
    },
    'A2A_CARD_GENERATED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent card generated',
        'alternative': 'Add to SystemEvents: A2A_CARD_GENERATED = "a2a.card.generated"'
    },
    'A2A_CARD_GENERATING': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent card generation started',
        'alternative': 'Add to SystemEvents: A2A_CARD_GENERATING = "a2a.card.generating"'
    },
    'A2A_CARD_EXPORTED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent card exported',
        'alternative': 'Add to SystemEvents: A2A_CARD_EXPORTED = "a2a.card.exported"'
    },
    'A2A_CARD_EXPORTING': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A agent card export started',
        'alternative': 'Add to SystemEvents: A2A_CARD_EXPORTING = "a2a.card.exporting"'
    },
    'A2A_SERVER_STOPPED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A server stopped',
        'alternative': 'Add to SystemEvents: A2A_SERVER_STOPPED = "a2a.server.stopped"'
    },
    'A2A_SERVER_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - A2A server failed',
        'alternative': 'Add to SystemEvents: A2A_SERVER_FAILED = "a2a.server.failed"'
    },
    
    # ============================================================================
    # DOCUMENT/CONTENT PROCESSING - USE EXISTING OR ADD
    # ============================================================================
    'DOCUMENT_PROCESSING_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.DOCUMENT_PROCESSING_FAILED (already exists)'
    },
    
    # ============================================================================
    # WEBHOOK EVENTS - ADD BACK
    # ============================================================================
    'WEBHOOK_FAILED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - webhook delivery failed',
        'alternative': 'Add to SystemEvents: WEBHOOK_FAILED = "webhook.failed"'
    },
    'WEBHOOK_SENT': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - webhook sent successfully',
        'alternative': 'Add to SystemEvents: WEBHOOK_SENT = "webhook.sent"'
    },
    
    # ============================================================================
    # WORKFLOW EVENTS - ADD BACK
    # ============================================================================
    'WORKFLOW_EXECUTION_STARTED': {
        'action': 'USE_EXISTING',
        'reason': 'Check if exists - workflow execution started',
        'alternative': 'Check SystemEvents.OVERLORD_WORKFLOW_STARTED or add WORKFLOW_EXECUTION_STARTED'
    },
    'WORKFLOW_EXECUTION_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.WORKFLOW_EXECUTION_FAILED (already exists)'
    },
    'WORKFLOW_EXECUTION_COMPLETED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - workflow execution completed',
        'alternative': 'Add to ConversationEvents: WORKFLOW_EXECUTION_COMPLETED = "workflow.execution.completed"'
    },
    'WORKFLOW_DECOMPOSITION_COMPLETED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - workflow decomposition completed',
        'alternative': 'Add to ConversationEvents: WORKFLOW_DECOMPOSITION_COMPLETED = "workflow.decomposition.completed"'
    },
    'WORKFLOW_DECOMPOSITION_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.WORKFLOW_DECOMPOSITION_FAILED (already exists)'
    },
    'WORKFLOW_ANALYSIS_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.WORKFLOW_ANALYSIS_FAILED (already exists)'
    },
    'WORKFLOW_TASK_ASSIGNED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - workflow task assigned to agent',
        'alternative': 'Add to ConversationEvents: WORKFLOW_TASK_ASSIGNED = "workflow.task.assigned"'
    },
    'WORKFLOW_TASK_COMPLETED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - workflow task completed',
        'alternative': 'Add to ConversationEvents: WORKFLOW_TASK_COMPLETED = "workflow.task.completed"'
    },
    
    # ============================================================================
    # SCHEDULER EVENTS - ADD BACK
    # ============================================================================
    'SCHEDULED_JOB_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.SCHEDULED_JOB_FAILED (already exists)'
    },
    'SCHEDULED_JOB_PAUSED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.SCHEDULED_JOB_PAUSED (already exists)'
    },
    'SCHEDULED_JOB_UPDATED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - scheduled job updated',
        'alternative': 'Add to SystemEvents: SCHEDULED_JOB_UPDATED = "scheduled.job.updated"'
    },
    
    # ============================================================================
    # MCP RUNTIME EVENTS - ADD BACK
    # ============================================================================
    'MCP_SERVER_REGISTERED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.MCP_SERVER_REGISTERED (already exists)'
    },
    'MCP_SERVER_REGISTRATION_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.MCP_SERVER_REGISTRATION_FAILED (already exists)'
    },
    'MCP_SERVER_UNREGISTERED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.MCP_SERVER_UNREGISTERED (already exists)'
    },
    'MCP_SERVER_DISCONNECTION_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.MCP_SERVER_DISCONNECTION_FAILED (already exists)'
    },
    
    # ============================================================================
    # MEMORY EVENTS - ADD BACK
    # ============================================================================
    'MEMORY_OPERATION_FAILED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in ErrorEvents',
        'alternative': 'Use ErrorEvents.MEMORY_OPERATION_FAILED (already exists)'
    },
    
    # ============================================================================
    # AGENT EVENTS - ADD BACK
    # ============================================================================
    'AGENT_REMOVED': {
        'action': 'USE_EXISTING',
        'reason': 'Event already exists in SystemEvents',
        'alternative': 'Use SystemEvents.AGENT_REMOVED (already exists)'
    },
    
    # ============================================================================
    # ERROR/VALIDATION EVENTS - USE EXISTING
    # ============================================================================
    'VALIDATION_ERROR': {
        'action': 'USE_EXISTING',
        'reason': 'Use generic validation failed event',
        'alternative': 'Use ErrorEvents.VALIDATION_FAILED (already exists)'
    },
    'TIMEOUT_ERROR': {
        'action': 'USE_EXISTING',
        'reason': 'Use generic timeout event',
        'alternative': 'Use ErrorEvents.CONNECTION_TIMEOUT (already exists)'
    },
    
    # ============================================================================
    # RESPONSE EVENTS - ADD BACK
    # ============================================================================
    'RESPONSE_SYNTHESIZED': {
        'action': 'ADD_BACK',
        'reason': 'Runtime event - response synthesis completed',
        'alternative': 'Add to ConversationEvents: RESPONSE_SYNTHESIZED = "response.synthesized"'
    },
    
    # ============================================================================
    # OTHER/MISC - NEED REVIEW
    # ============================================================================
    'SERVICE_WARNING': {
        'action': 'USE_EXISTING',
        'reason': 'Use generic warning event',
        'alternative': 'Use ErrorEvents.WARNING (already exists)'
    },
}


def analyze_and_recommend():
    """Analyze missing events and provide recommendations."""
    
    # Read CSV
    events_by_name = defaultdict(list)
    with open('event_validation_report.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['exists_in_enum'] == 'NO':
                events_by_name[row['event_name']].append(row)
    
    # Update recommendations in CSV
    output_rows = []
    for event_name, rows in events_by_name.items():
        rec = RECOMMENDATIONS.get(event_name, {
            'action': 'NEEDS_REVIEW',
            'reason': 'Not categorized - needs manual review',
            'alternative': 'Review context and decide: add back, use existing, or remove'
        })
        
        for row in rows:
            output_rows.append({
                **row,
                'action': rec['action'],
                'reason': rec['reason'],
                'recommendation': rec['alternative']
            })
    
    # Write updated CSV
    with open('event_recommendations.csv', 'w', newline='') as f:
        fieldnames = ['event_name', 'enum_category', 'exists_in_enum', 'action', 'reason', 'recommendation', 'file', 'line', 'context']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    
    # Generate summary
    action_counts = defaultdict(int)
    unique_by_action = defaultdict(set)
    
    for event_name, rows in events_by_name.items():
        rec = RECOMMENDATIONS.get(event_name, {'action': 'NEEDS_REVIEW'})
        action = rec['action']
        action_counts[action] += len(rows)
        unique_by_action[action].add(event_name)
    
    print(f"\n{'='*80}")
    print(f"EVENT RECOMMENDATION SUMMARY")
    print(f"{'='*80}\n")
    print(f"Total missing event references: {sum(action_counts.values())}")
    print(f"Unique missing events: {len(events_by_name)}")
    
    print(f"\nBy Action:")
    for action in sorted(action_counts.keys()):
        count = action_counts[action]
        unique_count = len(unique_by_action[action])
        print(f"  {action}: {count} references ({unique_count} unique events)")
    
    print(f"\nADD_BACK Events ({len(unique_by_action['ADD_BACK'])} unique):")
    for event in sorted(unique_by_action.get('ADD_BACK', [])):
        count = len(events_by_name[event])
        print(f"  - {event}: {count} locations")
    
    print(f"\nUSE_EXISTING Events ({len(unique_by_action['USE_EXISTING'])} unique):")
    for event in sorted(unique_by_action.get('USE_EXISTING', [])):
        count = len(events_by_name[event])
        rec = RECOMMENDATIONS[event]
        print(f"  - {event} → {rec['alternative']}")
    
    print(f"\nREMOVE Events ({len(unique_by_action['REMOVE'])} unique):")
    for event in sorted(unique_by_action.get('REMOVE', [])):
        count = len(events_by_name[event])
        print(f"  - {event}: {count} locations (init phase)")
    
    print(f"\nREMOVE_OR_REPLACE Events ({len(unique_by_action['REMOVE_OR_REPLACE'])} unique):")
    for event in sorted(unique_by_action.get('REMOVE_OR_REPLACE', [])):
        count = len(events_by_name[event])
        print(f"  - {event}: {count} locations (context-dependent)")
    
    print(f"\nNEEDS_REVIEW Events ({len(unique_by_action['NEEDS_REVIEW'])} unique):")
    for event in sorted(unique_by_action.get('NEEDS_REVIEW', [])):
        count = len(events_by_name[event])
        print(f"  - {event}: {count} locations")
    
    print(f"\nOutput file: event_recommendations.csv")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    analyze_and_recommend()
