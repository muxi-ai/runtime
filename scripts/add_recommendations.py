#!/usr/bin/env python3
"""
Add recommendation column to observability_events_audit.csv
Based on INITIALIZING_EVENTS_ANALYSIS.md findings
"""

import csv

# Define recommendations based on analysis
INITIALIZING_RECOMMENDATIONS = {
    # KEEP (18 events) - Not covered by InitEventFormatter
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "97"): "KEEP - Observability bootstrap (chicken-egg)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "234"): "KEEP - LLM config not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "277"): "KEEP - Working memory config (distinct from buffer/persistent)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "553"): "KEEP - Document processing not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "651"): "KEEP - Artifact service not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "765"): "KEEP - Clarification config not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "813"): "KEEP - Document config not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/formation.py", "3146"): "KEEP - Runtime event (not startup)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/formation.py", "3177"): "KEEP - Runtime event (not startup)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/formation.py", "3192"): "KEEP - Runtime event (not startup)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "482"): "KEEP - Credential resolver not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "2786"): "KEEP - A2A ClientFactory distinct from A2A server",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/server/server.py", "130"): "KEEP - Runtime event (not startup)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/server/server.py", "185"): "KEEP - Security warning (auto-generated keys)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/server/server.py", "226"): "KEEP - API keys config not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/workflow/workflow_manager.py", "51"): "KEEP - Workflow manager not in InitEventFormatter",
    ("SystemEvents.INITIALIZING", "src/muxi/services/llm/llm.py", "151"): "KEEP - LLM cache config (new Oct 2025 feature)",
    ("SystemEvents.INITIALIZING", "src/muxi/services/llm/llm.py", "173"): "KEEP - LLM cache config (new Oct 2025 feature)",
    
    # REMOVE - Redundant with InitEventFormatter (9 events)
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "339"): "REMOVE - Redundant (InitEventFormatter section 2: Buffer memory)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "456"): "REMOVE - Redundant (InitEventFormatter section 4: Persistent memory)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "604"): "REMOVE - Redundant (InitEventFormatter section 5: MCP per-server lines)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "708"): "REMOVE - Redundant (InitEventFormatter section 8: Scheduler service)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "1077"): "REMOVE - Redundant (InitEventFormatter section 4: Persistent memory)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "1120"): "REMOVE - Redundant (InitEventFormatter section 4: Persistent memory)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/formation.py", "1268"): "REMOVE - Redundant (InitEventFormatter section 10: Formation ready)",
    ("SystemEvents.INITIALIZING", "src/muxi/utils/run_formation.py", "64"): "REMOVE - Redundant (InitEventFormatter section 1: Formation banner)",
    ("SystemEvents.INITIALIZING", "src/muxi/utils/run_formation.py", "271"): "REMOVE - Redundant (InitEventFormatter section 1: Formation banner)",
    
    # REMOVE - DEBUG runtime traces (7 events)
    ("SystemEvents.INITIALIZING", "src/muxi/formation/artifacts/extractor.py", "41"): "REMOVE - DEBUG runtime trace (not initialization)",
    ("SystemEvents.INITIALIZING", "src/muxi/services/memory/long_term.py", "207"): "REMOVE - DEBUG runtime trace (lazy loading)",
    ("SystemEvents.INITIALIZING", "src/muxi/services/memory/long_term.py", "258"): "REMOVE - DEBUG runtime trace (internal detail)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "2738"): "REMOVE - DEBUG runtime trace (collection registration)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "2751"): "REMOVE - DEBUG runtime trace (collection registration)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "4148"): "REMOVE - DEBUG runtime trace (file processing)",
    ("SystemEvents.INITIALIZING", "src/muxi/formation/overlord/overlord.py", "4188"): "REMOVE - DEBUG runtime trace (file processing)",
    
    # CONVERT to ErrorEvent (1 event)
    ("SystemEvents.INITIALIZING", "src/muxi/formation/initialization.py", "636"): "CONVERT to ErrorEvents.MCP_INITIALIZATION_FAILED (ERROR using INITIALIZING)",
}

def add_recommendations():
    """Add recommendation column to CSV based on analysis"""
    
    input_file = "observability_events_audit.csv"
    output_file = "observability_events_audit.csv"
    
    rows = []
    
    # Read existing CSV
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        # Add recommendation column if not present
        if 'recommendation' not in fieldnames:
            fieldnames = list(fieldnames) + ['recommendation']
        
        for row in reader:
            # Create lookup key
            key = (row['event_type'], row['file'], row['line'])
            
            # Add recommendation if exists
            if key in INITIALIZING_RECOMMENDATIONS:
                row['recommendation'] = INITIALIZING_RECOMMENDATIONS[key]
            else:
                # Leave empty for non-INITIALIZING events (user will review)
                row['recommendation'] = row.get('recommendation', '')
            
            rows.append(row)
    
    # Write updated CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"✅ Added recommendation column to {output_file}")
    print(f"   Total rows: {len(rows)}")
    print(f"   INITIALIZING events with recommendations: {len([r for r in rows if r.get('recommendation')])}")
    
    # Summary stats
    keep_count = len([r for r in rows if r.get('recommendation', '').startswith('KEEP')])
    remove_count = len([r for r in rows if r.get('recommendation', '').startswith('REMOVE')])
    convert_count = len([r for r in rows if r.get('recommendation', '').startswith('CONVERT')])
    
    print(f"\n   INITIALIZING breakdown:")
    print(f"     KEEP:    {keep_count}")
    print(f"     REMOVE:  {remove_count}")
    print(f"     CONVERT: {convert_count}")
    print(f"     TOTAL:   {keep_count + remove_count + convert_count}")

if __name__ == '__main__':
    add_recommendations()
