---
allowed-tools: Grep, Read, LS
---

# Search

Search across all PRDs, epics, and tasks.

## Usage
```
/pm:search <query>
```

## Instructions

### 1. Search Locations

Search in:
- `.claude/prds/*.md` - All PRDs
- `.claude/epics/*/epic.md` - All epics
- `.claude/epics/*/*.md` - All tasks
- `.claude/epics/*/updates/*/` - Progress notes

### 2. Search Content

Search for query in:
- Frontmatter (name, description fields)
- Headers
- Body content
- Code blocks
- Comments

### 3. Display Results

```
🔍 Search Results for: "$ARGUMENTS"

PRDs ({count} matches):
  📄 {prd_name}
    Line {num}: {matching_line_with_context}
    
Epics ({count} matches):
  📚 {epic_name}
    Line {num}: {matching_line_with_context}
    File: .claude/epics/{epic}/epic.md
    
Tasks ({count} matches):
  📝 {epic}/{task_name}
    Line {num}: {matching_line_with_context}
    Issue: #{number}
    Status: {status}
    
Progress Notes ({count} matches):
  📊 Issue #{number}
    {matching_content}

Total: {total_count} matches found

{If many results}: Showing first 20 matches. Refine search for better results.
```

### 4. No Results

If no matches:
```
No results found for: "$ARGUMENTS"

Suggestions:
- Try different keywords
- Check spelling
- Use simpler terms
```

### 5. Smart Search

Detect special searches:
- If query looks like issue number (#123), search for that issue
- If query is status (open, closed), find all with that status
- If query is date-like, search for items created/updated on that date

## Important Notes

Case-insensitive search by default.
Show context around matches.
Limit output to prevent overwhelming results.