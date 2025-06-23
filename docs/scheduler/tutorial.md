# MUXI Scheduler Tutorial: From Zero to Proactive AI

**Learn to schedule recurring AI tasks using natural language**

## Introduction

Welcome to the MUXI Scheduler tutorial! By the end of this guide, you'll understand how to transform MUXI from a reactive assistant into a proactive AI agent that can automatically handle recurring tasks on your behalf.

### What You'll Learn

- How to enable and configure the scheduler
- Natural language patterns for scheduling tasks
- Managing scheduled jobs and handling failures
- Advanced scheduling techniques and best practices
- Monitoring and troubleshooting scheduled jobs

### Prerequisites

- MUXI Runtime installed and configured
- Basic familiarity with Formation YAML configuration
- A database connection (PostgreSQL or SQLite)

## Chapter 1: Setting Up the Scheduler

### Step 1: Enable Scheduler in Formation

Create or update your `formation.yaml` file:

```yaml
# formation.yaml
scheduler:
  enabled: true
  check_interval_minutes: 1
  max_concurrent_jobs: 5
  max_failures_before_pause: 3
  timezone: "America/New_York"

memory:
  persistent:
    connection_string: "${POSTGRES_DATABASE_URL}"

agents:
  - id: assistant
    system_message: "You are a helpful assistant that can handle scheduled tasks."
    llm_models:
      - text: "openai/gpt-4o"
```

### Step 2: Set Environment Variables

```bash
# Set your database connection
export POSTGRES_DATABASE_URL="postgresql://user:pass@localhost:5432/muxi_db"

# Or for SQLite (simpler for testing)
export POSTGRES_DATABASE_URL="sqlite:///./scheduler.db"
```

### Step 3: Initialize Your Formation

```python
import asyncio
from muxi.runtime.formation import Formation

async def setup_scheduler():
    # Load formation with scheduler enabled
    formation = Formation()
    formation.load("formation.yaml")
    overlord = await formation.start_overlord()
    
    # Schedule a daily reminder using natural language
    response = await overlord.chat(
        "Schedule a daily reminder at 9am to check my calendar and plan the day",
        user_id="tutorial_user"
    )
    
    print("Scheduling response:", response.content)
    return formation, overlord

# Run the setup
formation, overlord = asyncio.run(setup_scheduler())
```

### Expected Output

```
Scheduler running: True
Check interval: 1 minutes
Timezone: America/New_York
```

## Chapter 2: Your First Scheduled Task

### Step 1: Schedule a Simple Daily Task

```python
async def schedule_daily_reminder():
    # Use natural language to schedule a task
    response = await overlord.chat(
        "Schedule a daily reminder at 9am to check my calendar and plan the day",
        user_id="tutorial_user"
    )
    
    print("Scheduling response:", response.content)
    return response

# Schedule the task
response = await schedule_daily_reminder()
```

### Step 2: Verify the Job Was Created

```python
async def check_scheduled_jobs():
    # Using Formation API (recommended)
    jobs = await formation.get_user_jobs("tutorial_user")
    
    for job in jobs:
        print(f"\n📅 Job: {job['title']}")
        print(f"   ID: {job['id']}")
        print(f"   Schedule: {job['cron_expression']}")
        print(f"   Status: {job['status']}")
        print(f"   Created: {job['created_at']}")
        print(f"   Original prompt: {job['original_prompt']}")
    
    return jobs

# Check what jobs were created
jobs = await check_scheduled_jobs()
```

### Expected Output

```
📅 Job: Daily Calendar Check and Planning
   Schedule: 0 9 * * *
   Status: ACTIVE
   Created: 2025-06-22T10:30:00Z
   Original prompt: check my calendar and plan the day
```

## Chapter 3: Understanding Cron Expressions

### Basic Patterns

The scheduler converts natural language to cron expressions:

```python
# Test different natural language patterns
schedule_examples = [
    "every day at 9am",           # 0 9 * * *
    "every weekday at 2pm",       # 0 14 * * 1-5
    "every Monday at 10am",       # 0 10 * * 1
    "every hour during work",     # 0 9-17 * * 1-5
    "twice daily at 9am and 6pm", # 0 9,18 * * *
]

async def test_schedule_patterns():
    for pattern in schedule_examples:
        response = await overlord.chat(
            f"Parse this schedule: {pattern}",
            user_id="tutorial_user"
        )
        print(f"'{pattern}' -> {response.content}")

await test_schedule_patterns()
```

### Cron Expression Reference

```
Format: minute hour day_of_month month day_of_week
         │     │    │           │     │
         │     │    │           │     └─ 0-6 (Sunday=0)
         │     │    │           └─ 1-12 
         │     │    └─ 1-31
         │     └─ 0-23
         └─ 0-59

Examples:
0 9 * * *        # Every day at 9am
0 14 * * 1-5     # Weekdays at 2pm
*/30 9-17 * * *  # Every 30 min during work hours
0 9 1 * *        # First day of month at 9am
0 18 * * 5       # Every Friday at 6pm
```

## Chapter 4: Advanced Scheduling Patterns

### Weekly and Monthly Patterns

```python
async def schedule_weekly_tasks():
    weekly_tasks = [
        {
            "schedule": "Every Monday at 10am, review last week's progress",
            "description": "Weekly progress review"
        },
        {
            "schedule": "Every Friday at 5pm, send team update email",
            "description": "Weekly team updates"
        },
        {
            "schedule": "First Monday of each month, generate monthly reports",
            "description": "Monthly reporting"
        }
    ]
    
    for task in weekly_tasks:
        print(f"\nScheduling: {task['description']}")
        
        response = await overlord.chat(
            task["schedule"],
            user_id="tutorial_user"
        )
        
        print(f"Response: {response.content}")

await schedule_weekly_tasks()
```

### Complex Exclusion Rules

```python
async def schedule_with_exclusions():
    # Schedule task with holiday exclusions
    response = await overlord.chat(
        "Every weekday at 9am except holidays and December 25th, "
        "send daily briefing email",
        user_id="tutorial_user"
    )
    
    print("Scheduled with exclusions:", response.content)
    
    # Get the job details to see exclusion rules
    jobs = await scheduler.job_manager.get_jobs_for_user("tutorial_user")
    latest_job = jobs[-1]  # Most recent job
    
    print(f"\nExclusion rules: {latest_job.exclusion_rules}")

await schedule_with_exclusions()
```

## Chapter 5: Job Management and Monitoring

### Using the Formation API

The Formation API provides convenient methods for accessing scheduler data:

```python
async def explore_formation_api():
    # Get all active jobs
    active_jobs = await formation.get_active_jobs()
    print(f"📊 Total active jobs: {len(active_jobs)}")
    
    # Get jobs for specific user
    user_jobs = await formation.get_user_jobs("tutorial_user")
    print(f"👤 Your jobs: {len(user_jobs)}")
    
    # Get job audit trail
    if user_jobs:
        job_id = user_jobs[0]['id']
        audit_trail = await formation.get_job_audit_trail(job_id)
        
        print(f"\n📋 Audit trail for job {job_id}:")
        for event in audit_trail[:5]:
            print(f"   {event['timestamp']}: {event['action']}")
            if event['reason']:
                print(f"      Reason: {event['reason']}")
    
    # Get recent audit events
    recent_events = await formation.get_recent_audit_trail(limit=10)
    print(f"\n🔔 Recent scheduler events: {len(recent_events)}")

await explore_formation_api()
```

### Listing and Managing Jobs

```python
async def manage_jobs():
    # Get all user jobs using Formation API
    jobs = await formation.get_user_jobs("tutorial_user")
    
    print(f"📋 You have {len(jobs)} scheduled jobs:\n")
    
    for i, job in enumerate(jobs, 1):
        print(f"{i}. {job['title']}")
        print(f"   📅 Schedule: {job['cron_expression'] or job['scheduled_for']}")
        print(f"   ⚡ Status: {job['status']}")
        print(f"   📊 Runs: {job['total_runs']} total, {job['total_failures']} failures")
        
        if job['total_runs'] > 0:
            success_rate = (job['total_runs'] - job['total_failures']) / job['total_runs']
            print(f"   ✅ Success rate: {success_rate:.1%}")
        
        if job['last_run_at']:
            print(f"   🕐 Last run: {job['last_run_at']}")
            if job['last_run_status']:
                print(f"   📌 Result: {job['last_run_status']}")
        
        print()

await manage_jobs()
```

### Job Control Operations

```python
async def job_control_demo():
    # Get user's jobs using Formation API
    jobs = await formation.get_user_jobs("tutorial_user")
    
    if jobs:
        job = jobs[0]  # Use first job for demo
        job_id = job['id']
        
        # Get scheduler service for write operations
        scheduler = await overlord.get_scheduler_service()
        
        # Pause a job
        print(f"Pausing job: {job['title']}")
        await scheduler.manager.pause_job(job_id, "tutorial_user", "Demo pause")
        
        # Check audit trail
        audit_trail = await formation.get_job_audit_trail(job_id)
        latest_event = audit_trail[0]
        print(f"Latest event: {latest_event['action']} - {latest_event['reason']}")
        
        # Resume the job
        print(f"Resuming job: {job['title']}")
        await scheduler.manager.resume_job(job_id, "tutorial_user")
        
        # Delete a job (be careful!)
        # await scheduler.manager.delete_job(job_id, "tutorial_user", "Demo cleanup")
        # print(f"Deleted job: {job['title']}")

await job_control_demo()
```

## Chapter 6: Real-World Examples

### Email Management

```python
async def schedule_email_management():
    email_tasks = [
        "Every 2 hours during work hours, check for urgent emails and summarize",
        "Every day at 8am, send me a digest of yesterday's important emails",
        "Every Friday at 4pm, archive processed emails and clean inbox"
    ]
    
    for task in email_tasks:
        await overlord.chat(task, user_id="email_manager")
        
    print("Email management tasks scheduled!")

await schedule_email_management()
```

### Project Monitoring

```python
async def schedule_project_monitoring():
    monitoring_tasks = [
        "Every 4 hours, check project status and alert on any blockers",
        "Daily at 9am, review yesterday's commits and summarize changes",
        "Every Monday at 10am, generate weekly progress report",
        "First day of month, create monthly project health report"
    ]
    
    for task in monitoring_tasks:
        await overlord.chat(task, user_id="project_manager")
    
    print("Project monitoring scheduled!")

await schedule_project_monitoring()
```

### Content Creation

```python
async def schedule_content_creation():
    content_tasks = [
        "Every Tuesday at 2pm, brainstorm blog post ideas based on recent trends",
        "Every Thursday at 11am, draft social media posts for next week",
        "First Friday of month, create monthly newsletter draft"
    ]
    
    for task in content_tasks:
        await overlord.chat(task, user_id="content_creator")
    
    print("Content creation pipeline scheduled!")

await schedule_content_creation()
```

## Chapter 7: Error Handling and Recovery

### Handling Failed Jobs

```python
async def monitor_job_health():
    scheduler = overlord.scheduler_service
    jobs = await scheduler.job_manager.get_jobs_for_user("tutorial_user")
    
    failed_jobs = [job for job in jobs if job.consecutive_failures > 0]
    
    if failed_jobs:
        print("⚠️  Jobs with failures:")
        
        for job in failed_jobs:
            print(f"\n❌ {job.title}")
            print(f"   Consecutive failures: {job.consecutive_failures}")
            print(f"   Last failure: {job.last_run_failure_message}")
            
            # Reset failure count if you've fixed the issue
            if job.consecutive_failures < 3:
                await scheduler.job_manager.reset_failure_count(job.id)
                print("   ✅ Failure count reset")
    else:
        print("✅ All jobs healthy!")

await monitor_job_health()
```

### Automatic Recovery Strategies

```python
async def setup_recovery_strategies():
    # The scheduler has built-in recovery features:
    
    # 1. Automatic retry with exponential backoff
    # 2. Auto-pause after max consecutive failures
    # 3. Detailed failure logging and reporting
    
    scheduler = overlord.scheduler_service
    
    # Check current failure thresholds
    config = await scheduler.get_configuration()
    print(f"Max failures before pause: {config['max_failures_before_pause']}")
    
    # Monitor service health
    health = await scheduler.get_health_status()
    print(f"Service health: {health}")

await setup_recovery_strategies()
```

## Chapter 8: Performance and Optimization

### Monitoring Performance

```python
async def monitor_performance():
    scheduler = overlord.scheduler_service
    
    # Get overall scheduler statistics
    stats = await scheduler.get_scheduler_statistics()
    
    print("📊 Scheduler Performance:")
    print(f"   Active jobs: {stats['active_jobs_count']}")
    print(f"   Jobs processed today: {stats['jobs_processed_today']}")
    print(f"   Average execution time: {stats['avg_execution_time_ms']}ms")
    print(f"   Success rate: {stats['overall_success_rate']:.1%}")
    
    # Check for slow jobs
    slow_jobs = [job for job in stats['recent_executions'] 
                 if job['execution_time_ms'] > 5000]  # >5 seconds
    
    if slow_jobs:
        print(f"\n⚠️  {len(slow_jobs)} slow-running jobs detected")
        for job in slow_jobs:
            print(f"   {job['title']}: {job['execution_time_ms']}ms")

await monitor_performance()
```

### Optimization Tips

```python
async def optimization_demo():
    # 1. Batch similar operations
    batch_task = """
    Every 6 hours, batch process:
    - Check all email accounts
    - Update project statuses  
    - Generate summary report
    """
    
    # 2. Use appropriate intervals
    reasonable_intervals = [
        "Every 15 minutes - system health checks",
        "Every hour - email monitoring", 
        "Every 4 hours - data synchronization",
        "Daily - reports and summaries",
        "Weekly - comprehensive analysis"
    ]
    
    # 3. Optimize job prompts for efficiency
    efficient_prompt = """
    Check for urgent emails (priority: high, from: VIP list) 
    and provide 2-sentence summary of any actionable items
    """
    
    print("💡 Optimization strategies implemented")

await optimization_demo()
```

## Chapter 9: Advanced Features

### Dynamic Job Modification

```python
async def dynamic_job_modification():
    scheduler = overlord.scheduler_service
    
    # Create a job
    response = await overlord.chat(
        "Every day at 10am, check weather and suggest outfit",
        user_id="tutorial_user"
    )
    
    # Get the job
    jobs = await scheduler.job_manager.get_jobs_for_user("tutorial_user")
    weather_job = next((job for job in jobs if "weather" in job.title.lower()), None)
    
    if weather_job:
        # Modify the schedule (change time)
        await scheduler.job_manager.update_job_schedule(
            weather_job.id, 
            "0 8 * * *"  # Change from 10am to 8am
        )
        
        # Update the prompt
        await scheduler.job_manager.update_job_prompt(
            weather_job.id,
            "Check weather, air quality, and traffic. Suggest optimal outfit and commute time."
        )
        
        print("✅ Job updated successfully")

await dynamic_job_modification()
```

### Conditional Execution

```python
async def conditional_execution_example():
    # Jobs can include conditional logic in their prompts
    conditional_tasks = [
        """
        Every morning at 7am:
        - Check weather forecast
        - If rain >50% probability, send umbrella reminder
        - If temperature <32°F, send warm clothing alert
        """,
        
        """
        Every hour during trading hours:
        - Check portfolio performance
        - If loss >5%, send risk alert
        - If gain >10%, send profit-taking suggestion
        """,
        
        """
        Every 6 hours:
        - Check server metrics
        - If CPU >80% or memory >90%, send alert
        - If all green, log status confirmation
        """
    ]
    
    for task in conditional_tasks:
        await overlord.chat(task, user_id="advanced_user")
    
    print("🎯 Conditional execution jobs scheduled")

await conditional_execution_example()
```

## Chapter 10: Integration Patterns

### MCP Tool Integration

```python
async def schedule_mcp_tool_usage():
    # Schedule tasks that use MCP tools
    mcp_tasks = [
        "Every 2 hours, use the file_search tool to find recent documents and summarize",
        "Daily at 9am, use the database_query tool to generate daily metrics report", 
        "Every Monday, use the api_client tool to sync data with external systems"
    ]
    
    for task in mcp_tasks:
        await overlord.chat(task, user_id="mcp_user")
    
    print("🔧 MCP tool integration scheduled")

await schedule_mcp_tool_usage()
```

### Multi-Agent Coordination

```python
async def schedule_multi_agent_tasks():
    # Schedule tasks that involve multiple agents
    coordination_tasks = [
        "Every morning, coordinate with research agent to brief analysis agent",
        "Daily at 5pm, have summary agent collect updates from all project agents",
        "Weekly, schedule planning session between strategy and execution agents"
    ]
    
    for task in coordination_tasks:
        await overlord.chat(task, user_id="coordinator")
    
    print("🤝 Multi-agent coordination scheduled")

await schedule_multi_agent_tasks()
```

## Chapter 11: Troubleshooting Guide

### Common Issues and Solutions

```python
async def troubleshooting_guide():
    # Issue 1: Jobs not executing
    print("🔍 Troubleshooting Common Issues:\n")
    
    # Check if scheduler is running
    scheduler = overlord.scheduler_service
    status = await scheduler.get_service_status()
    
    if not status['running']:
        print("❌ Issue: Scheduler not running")
        print("   Solution: Check formation.yaml has scheduler.enabled: true")
        return
    
    # Check database connectivity
    try:
        jobs = await scheduler.job_manager.get_active_jobs()
        print("✅ Database connection OK")
    except Exception as e:
        print(f"❌ Database issue: {e}")
        print("   Solution: Verify connection string in formation.yaml")
        return
    
    # Check for paused jobs
    user_jobs = await scheduler.job_manager.get_jobs_for_user("tutorial_user")
    paused_jobs = [job for job in user_jobs if job.status == 'PAUSED']
    
    if paused_jobs:
        print(f"⚠️  Found {len(paused_jobs)} paused jobs")
        for job in paused_jobs:
            print(f"   - {job.title} (failures: {job.consecutive_failures})")
        print("   Solution: Review failures and reactivate jobs if issues are resolved")
    
    # Check timezone configuration
    if status.get('timezone') != 'America/New_York':
        print(f"⚠️  Timezone mismatch: {status.get('timezone')}")
        print("   Solution: Verify timezone setting matches your location")
    
    print("\n✅ Troubleshooting complete")

await troubleshooting_guide()
```

### Debug Mode and Logging

```python
import logging

async def enable_debug_mode():
    # Enable debug logging
    logging.getLogger('muxi.runtime.services.scheduler').setLevel(logging.DEBUG)
    
    print("🐛 Debug mode enabled")
    print("   - Job discovery details will be logged")
    print("   - Execution timing information included")
    print("   - Database query details shown")
    
    # Test a job execution with debug output
    scheduler = overlord.scheduler_service
    
    # Manually trigger job processing (for testing)
    # This would normally happen automatically
    await scheduler._process_due_jobs()

await enable_debug_mode()
```

## Chapter 12: Production Deployment

### Production Configuration

```yaml
# production-formation.yaml
scheduler:
  enabled: true
  check_interval_minutes: 1
  max_concurrent_jobs: 20        # Higher for production
  max_failures_before_pause: 5   # More tolerant
  timezone: "UTC"                # Use UTC in production

memory:
  persistent:
    connection_string: "${POSTGRES_DATABASE_URL}"  # Production PostgreSQL

observability:
  enabled: true
  transports:
    - type: "datadog"           # Production monitoring
      api_key: "${DD_API_KEY}"
```

### Health Monitoring

```python
async def production_health_check():
    scheduler = overlord.scheduler_service
    
    # Comprehensive health check
    health_report = {
        'service_status': await scheduler.get_service_status(),
        'database_health': await scheduler.test_database_connection(),
        'job_statistics': await scheduler.get_scheduler_statistics(),
        'recent_errors': await scheduler.get_recent_errors(limit=10)
    }
    
    # Example health endpoint response
    return {
        'status': 'healthy' if health_report['service_status']['running'] else 'unhealthy',
        'details': health_report,
        'timestamp': datetime.utcnow().isoformat()
    }

health_status = await production_health_check()
print(f"Production health: {health_status['status']}")
```

## Conclusion

Congratulations! 🎉 You've completed the MUXI Scheduler tutorial. You now know how to:

- ✅ Configure and enable the scheduler
- ✅ Create scheduled tasks using natural language
- ✅ Manage job lifecycles and handle failures
- ✅ Monitor performance and troubleshoot issues
- ✅ Implement advanced scheduling patterns
- ✅ Deploy in production environments

### Next Steps

1. **Explore Your Use Cases**: Identify repetitive tasks in your workflow
2. **Start Simple**: Begin with basic daily/weekly schedules
3. **Iterate and Improve**: Monitor job performance and optimize
4. **Scale Up**: Add more complex scheduling as you gain confidence

### Resources

- **API Reference**: `/docs/scheduler/README.md`
- **Implementation Details**: `/context/plans/scheduler-feature-implementation-plan.md`
- **Test Examples**: `/tests/scheduler/`
- **Formation Templates**: `/examples/configs/`

The MUXI Scheduler transforms static AI assistants into proactive digital agents. Start scheduling your recurring tasks today and experience the power of proactive AI! 🚀