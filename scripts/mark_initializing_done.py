#!/usr/bin/env python3
"""
Mark all INITIALIZING events as "done" in observability_events_audit.csv
"""

import csv

def mark_initializing_done():
    """Add status column and mark INITIALIZING events as done"""
    
    input_file = "observability_events_audit.csv"
    output_file = "observability_events_audit.csv"
    
    rows = []
    
    # Read existing CSV
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        
        # Add status column if not present
        if 'status' not in fieldnames:
            fieldnames.append('status')
        
        for row in reader:
            # Mark INITIALIZING events as done
            if row['event_type'] == 'SystemEvents.INITIALIZING':
                row['status'] = 'done'
            else:
                row['status'] = row.get('status', '')
            
            rows.append(row)
    
    # Write updated CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Count done events
    done_count = len([r for r in rows if r.get('status') == 'done'])
    initializing_count = len([r for r in rows if r['event_type'] == 'SystemEvents.INITIALIZING'])
    
    print(f"✅ Updated {input_file}")
    print(f"   Total INITIALIZING events: {initializing_count}")
    print(f"   Marked as done: {done_count}")
    print(f"   Total rows: {len(rows)}")

if __name__ == '__main__':
    mark_initializing_done()
