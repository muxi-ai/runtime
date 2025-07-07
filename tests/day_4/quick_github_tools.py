#!/usr/bin/env python3
"""Quick list of GitHub MCP tools from previous test output"""

# From the test output logs, here are the 67 GitHub MCP tools discovered:
tools = [
    "add_issue_comment",
    "add_pull_request_review_comment_to_pending_review", 
    "assign_copilot_to_issue",
    "cancel_workflow_run",
    "create_and_submit_pull_request_review",
    "create_branch",
    "create_issue",
    "create_or_update_file",
    "create_pending_pull_request_review",
    "create_pull_request",
    "create_repository",
    "delete_file",
    "delete_pending_pull_request_review",
    "delete_workflow_run_logs",
    "dismiss_notification",
    "download_workflow_run_artifact",
    "fork_repository",
    "get_code_scanning_alert",
    "get_commit",
    "get_file_contents",
    "get_issue",
    "get_issue_comments",
    "get_job_logs",
    "get_me",
    "get_notification_details",
    "get_pull_request",
    "get_pull_request_comments",
    "get_pull_request_diff",
    "get_pull_request_files",
    "get_pull_request_reviews",
    "get_pull_request_status",
    "get_secret_scanning_alert",
    "get_tag",
    "get_workflow_run",
    "get_workflow_run_logs",
    "get_workflow_run_usage",
    "list_branches",
    "list_code_scanning_alerts",
    "list_commits",
    "list_issues",
    "list_notifications",
    "list_pull_requests",
    "list_secret_scanning_alerts",
    "list_tags",
    "list_workflow_jobs",
    "list_workflow_run_artifacts",
    "list_workflow_runs",
    "list_workflows",
    "manage_notification_subscription",
    "manage_repository_notification_subscription",
    "mark_all_notifications_read",
    "merge_pull_request",
    "push_files",
    "request_copilot_review",
    "rerun_failed_jobs",
    "rerun_workflow_run",
    "run_workflow",
    "search_code",
    "search_issues",
    "search_orgs",
    "search_pull_requests",
    "search_repositories",
    "search_users",
    "submit_pending_pull_request_review",
    "update_issue",
    "update_pull_request",
    "update_pull_request_branch"
]

print("=== GitHub MCP Tools (67 total) ===\n")

# Group by category
categories = {
    "Issues": [],
    "Pull Requests": [],
    "Files/Repository": [],
    "Workflows": [],
    "Search": [],
    "Notifications": [],
    "Other": []
}

for tool in tools:
    if "issue" in tool:
        categories["Issues"].append(tool)
    elif "pull_request" in tool or "pr_" in tool:
        categories["Pull Requests"].append(tool)
    elif any(x in tool for x in ["file", "repository", "branch", "commit", "tag"]):
        categories["Files/Repository"].append(tool)
    elif "workflow" in tool or "job" in tool:
        categories["Workflows"].append(tool)
    elif "search" in tool:
        categories["Search"].append(tool)
    elif "notification" in tool:
        categories["Notifications"].append(tool)
    else:
        categories["Other"].append(tool)

for category, tool_list in categories.items():
    if tool_list:
        print(f"\n{category} ({len(tool_list)} tools):")
        for tool in sorted(tool_list):
            print(f"  - {tool}")

print("\n\nNOTE: There are NO gist-specific tools in the GitHub MCP!")