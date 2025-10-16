#!/usr/bin/env python3
"""
Add recommendations to ALL events in observability_events_audit.csv
Based on OBSERVABILITY_REDUNDANCY_ANALYSIS.md findings
"""

import csv

def get_recommendation(event_type, level, description, file_path, line_num):
    """Return recommendation based on event analysis"""
    
    # Already handled INITIALIZING events
    if event_type == "SystemEvents.INITIALIZING":
        return "done"
    
    # ================================================================
    # CRITICAL: ErrorEvents.INTERNAL_ERROR (158 occurrences)
    # ================================================================
    if event_type == "ErrorEvents.INTERNAL_ERROR":
        # Categorize by description/context
        desc_lower = description.lower()
        
        if "memory" in desc_lower and "initialize" in desc_lower:
            return "REPLACE with ErrorEvents.MEMORY_INITIALIZATION_FAILED"
        elif "memory" in desc_lower and ("retrieval" in desc_lower or "failed" in desc_lower):
            return "REPLACE with ErrorEvents.MEMORY_OPERATION_FAILED"
        elif "knowledge" in desc_lower and "search" in desc_lower:
            return "REPLACE with ErrorEvents.KNOWLEDGE_SEARCH_FAILED"
        elif "a2a" in desc_lower or "agent-to-agent" in desc_lower:
            return "REPLACE with ErrorEvents.A2A_MESSAGE_HANDLING_FAILED (already exists)"
        elif "planning" in desc_lower and "template" in desc_lower:
            return "REPLACE with ErrorEvents.PLANNING_TEMPLATE_MISSING"
        elif "parameter" in desc_lower and "validat" in desc_lower:
            return "REPLACE with ErrorEvents.PARAMETER_VALIDATION_FAILED (already exists)"
        elif "embedding" in desc_lower:
            return "REPLACE with ErrorEvents.EMBEDDINGS_GENERATION_FAILED"
        elif "metadata" in desc_lower and "persist" in desc_lower:
            return "REPLACE with ErrorEvents.METADATA_PERSISTENCE_FAILED"
        elif "reference" in desc_lower and "persist" in desc_lower:
            return "REPLACE with ErrorEvents.REFERENCE_PERSISTENCE_FAILED"
        elif "document" in desc_lower:
            return "REPLACE with ErrorEvents.DOCUMENT_PROCESSING_FAILED (already exists)"
        elif "formation" in desc_lower and "init" in desc_lower:
            return "REPLACE with ErrorEvents.FORMATION_INITIALIZATION_FAILED"
        else:
            return "REPLACE with specific ErrorEvent type (INTERNAL_ERROR too generic)"
    
    # ================================================================
    # CRITICAL: ErrorEvents.RETRY_ATTEMPTED (81 occurrences)
    # ================================================================
    if event_type == "ErrorEvents.RETRY_ATTEMPTED":
        # These are ALL misnamed - they're errors, not retries
        desc_lower = description.lower()
        
        if "knowledge" in desc_lower and "search" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_SEARCH_FAILED"
        elif "knowledge" in desc_lower and "add" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_SOURCE_ADD_FAILED"
        elif "knowledge" in desc_lower and "create" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.KNOWLEDGE_HANDLER_CREATION_FAILED"
        elif "a2a" in desc_lower and ("authenticat" in desc_lower or "auth" in desc_lower):
            return "MISNOMER - REPLACE with ErrorEvents.A2A_AUTHENTICATION_FAILED"
        elif "a2a" in desc_lower and "credential" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.A2A_CREDENTIAL_LOAD_FAILED"
        elif "memory" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.MEMORY_OPERATION_FAILED"
        elif "multimodal" in desc_lower:
            return "MISNOMER - REPLACE with ErrorEvents.MULTIMODAL_PROCESSING_FAILED"
        else:
            return "MISNOMER - No retry happening! Replace with specific error type"
    
    # ================================================================
    # CRITICAL: ServerEvents.SERVER_STARTED (38 occurrences)
    # ================================================================
    if event_type == "ServerEvents.SERVER_STARTED":
        # Check if it's legitimate server start or misused debug trace
        if "server.py" in file_path and "started successfully" in description.lower():
            return "KEEP - Legitimate server start event"
        elif "run_formation.py" in file_path:
            return "KEEP - Legitimate server start event"
        elif "overlord.py" in file_path:
            # These are all misused debug traces
            return "REMOVE - Misused as debug trace in overlord.py (not server start)"
        else:
            return "REVIEW - Check if legitimate server start or debug trace"
    
    # ================================================================
    # CRITICAL: ErrorEvents.WARNING (33 occurrences)
    # ================================================================
    if event_type == "ErrorEvents.WARNING":
        # Anti-pattern: using level as event type
        desc_lower = description.lower()
        
        if "markitdown" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.MARKITDOWN_INIT_FAILED (level=WARNING)"
        elif "knowledge source" in desc_lower and ("not exist" in desc_lower or "missing" in desc_lower):
            return "ANTI-PATTERN - REPLACE with ErrorEvents.KNOWLEDGE_SOURCE_MISSING (level=WARNING)"
        elif "file" in desc_lower and "size" in desc_lower and "limit" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.FILE_SIZE_LIMIT_EXCEEDED (level=WARNING)"
        elif "json" in desc_lower and "parse" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.JSON_PARSE_FAILED (level=WARNING)"
        elif "artifact" in desc_lower and ("field" in desc_lower or "missing" in desc_lower):
            return "ANTI-PATTERN - REPLACE with ErrorEvents.ARTIFACT_FIELD_MISSING (level=WARNING)"
        elif "thumbnail" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.THUMBNAIL_GENERATION_FAILED (level=WARNING)"
        elif "memory" in desc_lower and "retrieval" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.MEMORY_RETRIEVAL_FAILED (level=WARNING)"
        elif "memory" in desc_lower and "clear" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.MEMORY_CLEAR_FAILED (level=WARNING)"
        elif "sop" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.SOP_INITIALIZATION_FAILED (level=WARNING)"
        elif "persona" in desc_lower and "file" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.PERSONA_FILE_MISSING (level=WARNING)"
        elif "secret" in desc_lower and "interpolat" in desc_lower:
            return "ANTI-PATTERN - REPLACE with ErrorEvents.SECRET_INTERPOLATION_FAILED (level=WARNING)"
        else:
            return "ANTI-PATTERN - Don't use level (WARNING) as event type! Create specific ErrorEvent"
    
    # ================================================================
    # Other patterns to flag
    # ================================================================
    
    # Generic/catch-all events that should be more specific
    if event_type in ["ErrorEvents.GENERIC_ERROR", "ErrorEvents.VALIDATION_ERROR", 
                      "SystemEvents.OPERATION_COMPLETED"]:
        return "REVIEW - Generic event type, consider more specific event"
    
    # NO DESCRIPTION events
    if description == "NO DESCRIPTION":
        return "MISSING DESCRIPTION - Add meaningful description"
    
    # DEBUG level events (potentially too granular)
    if level == "DEBUG" and event_type.startswith("ConversationEvents"):
        return "REVIEW - DEBUG ConversationEvent, may be too granular for production"
    
    # Events that are INFO level but might be DEBUG
    if level == "INFO" and any(word in description.lower() for word in ["processing step", "iteration", "parsing"]):
        return "REVIEW - Consider DEBUG level for granular processing steps"
    
    # Default - no recommendation
    return ""

def add_all_recommendations():
    """Add recommendations to all events in CSV"""
    
    input_file = "observability_events_audit.csv"
    output_file = "observability_events_audit.csv"
    
    rows = []
    
    # Read existing CSV
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        
        # Ensure we have recommendation column
        if 'recommendation' not in fieldnames:
            fieldnames.append('recommendation')
        
        for row in reader:
            # Skip if already has recommendation (INITIALIZING events)
            if not row.get('recommendation'):
                # Generate recommendation
                row['recommendation'] = get_recommendation(
                    row['event_type'],
                    row['level'],
                    row['description'],
                    row['file'],
                    row['line']
                )
            
            rows.append(row)
    
    # Write updated CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Summary statistics
    total = len(rows)
    with_recs = len([r for r in rows if r.get('recommendation')])
    done = len([r for r in rows if r.get('recommendation') == 'done'])
    
    # Category breakdown
    internal_error = len([r for r in rows if r['event_type'] == 'ErrorEvents.INTERNAL_ERROR'])
    retry_attempted = len([r for r in rows if r['event_type'] == 'ErrorEvents.RETRY_ATTEMPTED'])
    server_started = len([r for r in rows if r['event_type'] == 'ServerEvents.SERVER_STARTED'])
    warning_type = len([r for r in rows if r['event_type'] == 'ErrorEvents.WARNING'])
    
    internal_error_recs = len([r for r in rows if r['event_type'] == 'ErrorEvents.INTERNAL_ERROR' and r.get('recommendation')])
    retry_attempted_recs = len([r for r in rows if r['event_type'] == 'ErrorEvents.RETRY_ATTEMPTED' and r.get('recommendation')])
    server_started_recs = len([r for r in rows if r['event_type'] == 'ServerEvents.SERVER_STARTED' and r.get('recommendation')])
    warning_type_recs = len([r for r in rows if r['event_type'] == 'ErrorEvents.WARNING' and r.get('recommendation')])
    
    print(f"✅ Updated {output_file}")
    print(f"\nTotal events: {total}")
    print(f"Events with recommendations: {with_recs} ({100*with_recs//total}%)")
    print(f"  - Done (INITIALIZING): {done}")
    print(f"\nCritical Issues Flagged:")
    print(f"  - INTERNAL_ERROR: {internal_error_recs}/{internal_error}")
    print(f"  - RETRY_ATTEMPTED: {retry_attempted_recs}/{retry_attempted}")
    print(f"  - SERVER_STARTED: {server_started_recs}/{server_started}")
    print(f"  - WARNING (anti-pattern): {warning_type_recs}/{warning_type}")
    print(f"\nTotal flagged for review/fix: {with_recs - done}")

if __name__ == '__main__':
    add_all_recommendations()
