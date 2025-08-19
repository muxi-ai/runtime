---
allowed-tools: Read, LS
---

# PRD Status

Show status of all PRDs and their implementation progress.

## Usage
```
/pm:prd-status
```

## Instructions

### 1. Scan PRDs

Read all files in `.claude/prds/`:
- Parse frontmatter for status
- Check for associated epics

### 2. Check Implementation

For each PRD:
- Look for epic in `.claude/epics/{prd_name}/`
- If epic exists, get progress from epic frontmatter
- Check if epic is synced to GitHub

### 3. Display Status

```
📋 PRD Implementation Status

Not Started:
  {prd_name}
    Created: {date}
    Status: backlog
    Epic: None
    
In Progress:
  {prd_name}
    Created: {date}
    Epic: {epic_name} ({progress}% complete)
    Tasks: {open}/{total}
    GitHub: {synced|not synced}
    
Completed:
  {prd_name}
    Created: {date}
    Completed: {date}
    Epic: {epic_name} (100% complete)
    Duration: {days}

Summary:
  Total PRDs: {count}
  Not Started: {count}
  In Progress: {count} (avg {avg}% complete)
  Completed: {count}
  
Next Actions:
  {If backlog PRDs}: Create epics with /pm:prd-parse
  {If in-progress}: Continue work with /pm:next
  {If all complete}: Create new PRD with /pm:prd-new
```

### 4. Detailed View Option

For each PRD, offer:
"View details: /pm:prd-list for full list"

## Important Notes

Show clear relationship between PRDs and epics.
Highlight PRDs without implementation.
Calculate accurate progress metrics.