# PRD List

List all existing Product Requirements Documents.

## Usage
```
/pm:prd-list
```

## Instructions

You are listing all PRDs in the project.

### 1. Scan PRD Directory
- Read the `.claude/prds/` directory
- List all `.md` files found
- Parse frontmatter from each PRD file to extract metadata

### 2. Display Format
For each PRD found, display using frontmatter data:
```
📋 {name} ({status})
   Description: {description}
   File: .claude/prds/{filename}
   Created: {created}
   Status: {status}
```

### 3. Status-Based Grouping
Group PRDs by status:
```
🔍 Backlog PRDs:
   📋 user-authentication - User authentication and authorization system
   📋 payment-system - Payment processing and billing management

🔄 In-Progress PRDs:
   📋 notification-service - Real-time notification system

✅ Implemented PRDs:
   📋 user-profiles - User profile management features
```

### 4. Summary
Display summary statistics:
```
📊 PRD Summary
   Total PRDs: {total_count}
   Backlog: {backlog_count}
   In-Progress: {in_progress_count}
   Implemented: {implemented_count}
   
📅 Recent Activity
   Most recent: {most_recent_name} ({created_date})
   Oldest: {oldest_name} ({created_date})
```

### 5. Suggested Actions
Based on PRD statuses:
- For backlog PRDs: suggest parsing to epic with `/pm:prd-parse {name}`
- For in-progress PRDs: suggest checking epic status with `/pm:epic-show {name}`
- For implemented PRDs: suggest reviewing for lessons learned

If no PRDs exist, suggest creating one with `/pm:prd-new`.

Parse frontmatter carefully to extract accurate metadata for each PRD in the display.
