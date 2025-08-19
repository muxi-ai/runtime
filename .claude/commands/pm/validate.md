---
allowed-tools: Read, LS, Grep
---

# Validate

Check PM system integrity for issues.

## Usage
```
/pm:validate
```

## Instructions

### 1. Check Frontmatter Validity

For all .md files in `.claude/prds/` and `.claude/epics/`:
- Verify frontmatter exists and is valid YAML
- Check required fields (name, status, created)
- Verify dates are valid ISO format
- Check status values are valid for file type

### 2. Check References

Verify all references are valid:
- Epic files reference existing PRDs
- Task files reference valid epic
- GitHub URLs are properly formatted
- Dependencies reference existing tasks

### 3. Check Consistency

- Task counts match (epic summary vs actual files)
- Progress calculations are correct
- No orphaned task files (tasks without epic)
- No duplicate issue numbers

### 4. Check GitHub Sync

For files with GitHub URLs:
- Verify URL format is correct
- Check for duplicate GitHub issue assignments
- Note files marked as synced but modified after last_sync

### 5. Display Report

```
🔍 Validation Report

✅ Valid Files: {count}
⚠️ Issues Found: {count}

Issues:
  {file_path}:
    - {issue_description}
    - {suggested_fix}
    
  {file_path}:
    - {issue_description}
    - {suggested_fix}

Orphaned Files:
  {list_of_files_without_proper_parent}

Sync Issues:
  {list_of_files_needing_sync}

Summary:
  {If no issues}: ✅ All checks passed - system healthy
  {If issues}: ⚠️ {count} issues found - run suggested fixes
```

### 6. Auto-fix Option

For simple issues, offer:
"Auto-fix {count} simple issues? (yes/no)"

Simple fixes:
- Missing required frontmatter fields (use defaults)
- Invalid date formats (convert to ISO)
- Progress calculation mismatches (recalculate)

## Important Notes

Don't modify files unless user approves auto-fix.
Report all issues, even minor ones.
Provide actionable fix suggestions.