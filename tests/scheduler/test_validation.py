"""
MUXI Scheduler Validation Tests

Unit tests for the scheduler validation and limits modules.
Tests all validation logic and resource limiting functionality.
"""

import pytest
import sys
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

try:
    from muxi.runtime.services.scheduler.validation import (
        SchedulerInputValidator,
        SchedulerSecurityError,
        validate_user_access
    )
    from muxi.runtime.services.scheduler.limits import (
        ResourceLimits,
        RateLimiter,
        SchedulerLimitsEnforcer,
        get_limits_enforcer,
        configure_limits
    )
    from muxi.runtime.utils.datetime_utils import utc_now
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    print(f"Warning: Could not import scheduler modules: {e}")
    print("Skipping validation tests")


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestSchedulerInputValidator:
    """Test the SchedulerInputValidator class."""
    
    def test_sanitize_schedule_text_valid_inputs(self):
        """Test sanitization of valid inputs."""
        valid_inputs = [
            "every day at 9am",
            "weekly on Monday",
            "every 15 minutes",
            "daily at noon",
            "monthly on the 1st",
            "every hour during business hours",
            "weekdays at 5pm",
        ]
        
        for input_text in valid_inputs:
            result = SchedulerInputValidator.sanitize_schedule_text(input_text)
            assert result == input_text
    
    def test_sanitize_schedule_text_whitespace_normalization(self):
        """Test whitespace normalization."""
        test_cases = [
            ("  every   day   at   9am  ", "every day at 9am"),
            ("\\t\\nweekly\\t\\n", "weekly"),
            ("daily\\n\\nat\\nnoon", "daily at noon"),
        ]
        
        for input_text, expected in test_cases:
            result = SchedulerInputValidator.sanitize_schedule_text(input_text)
            assert result == expected
    
    def test_sanitize_schedule_text_dangerous_patterns(self):
        """Test removal of dangerous patterns."""
        dangerous_cases = [
            ("schedule ```bash rm -rf /``` daily", "schedule  daily"),
            ("every <script>alert('xss')</script> day", "every  day"),
            ("daily {\"exec\": \"rm -rf /\"}", "daily "),
            ("weekly `dangerous` schedule", "weekly  schedule"),
            ("javascript:alert('hack') daily", " daily"),
            ("data:text/html,<h1>hack</h1> weekly", " weekly"),
            ("file:///etc/passwd hourly", " hourly"),
            ("eval('code') every day", " every day"),
            ("exec('hack') weekly", " weekly"),
            ("import os; daily", " daily"),
            ("from subprocess import call; weekly", "; weekly"),
            ("__import__('os') daily", " daily"),
            ("os.system('hack') weekly", " weekly"),
            ("subprocess.call(['rm']) daily", " daily"),
            ("shell=True weekly", " weekly"),
        ]
        
        for input_text, expected_contains in dangerous_cases:
            result = SchedulerInputValidator.sanitize_schedule_text(input_text)
            # Check that dangerous patterns are removed
            assert "rm -rf" not in result
            assert "script>" not in result
            assert "javascript:" not in result
            assert "exec(" not in result
            assert "eval(" not in result
            assert "{" not in result
            assert "}" not in result
            assert "`" not in result
            assert "<" not in result
            assert ">" not in result
            # Check that scheduling keywords remain
            scheduling_words = ["daily", "weekly", "schedule", "day", "hourly", "every"]
            assert any(word in result.lower() for word in scheduling_words)
    
    def test_sanitize_schedule_text_edge_cases(self):
        """Test edge cases for sanitization."""
        # Empty string
        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerInputValidator.sanitize_schedule_text("")
        
        # None input
        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerInputValidator.sanitize_schedule_text(None)
        
        # Non-string input
        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerInputValidator.sanitize_schedule_text(123)
        
        # Too long input
        long_text = "a" * 1001
        with pytest.raises(ValueError, match="too long"):
            SchedulerInputValidator.sanitize_schedule_text(long_text)
        
        # Input that becomes empty after sanitization
        only_dangerous = "```code``` <script> {json} `exec`"
        with pytest.raises(ValueError, match="empty after sanitization"):
            SchedulerInputValidator.sanitize_schedule_text(only_dangerous)
    
    def test_validate_user_id(self):
        """Test user ID validation."""
        # Valid user IDs
        valid_ids = [
            "user123",
            "test_user",
            "user-name",
            "user.name",
            "a1b2c3",
            "user_123-test.name",
            "1234567890",
        ]
        
        for user_id in valid_ids:
            SchedulerInputValidator.validate_user_id(user_id)  # Should not raise
        
        # Invalid user IDs
        invalid_cases = [
            ("", "non-empty string"),
            (None, "non-empty string"),
            (123, "non-empty string"),
            ("a" * 256, "too long"),
            ("user@name", "invalid characters"),
            ("user name", "invalid characters"),
            ("user/name", "invalid characters"),
            ("user\\name", "invalid characters"),
            ("user#name", "invalid characters"),
            ("user%name", "invalid characters"),
        ]
        
        for invalid_id, expected_error in invalid_cases:
            with pytest.raises(ValueError, match=expected_error):
                SchedulerInputValidator.validate_user_id(invalid_id)
    
    def test_validate_formation_id(self):
        """Test formation ID validation."""
        # Valid formation IDs (same rules as user IDs)
        valid_ids = [
            "formation123",
            "test_formation",
            "formation-name",
            "formation.name",
        ]
        
        for formation_id in valid_ids:
            SchedulerInputValidator.validate_formation_id(formation_id)
        
        # Invalid formation IDs
        with pytest.raises(ValueError, match="invalid characters"):
            SchedulerInputValidator.validate_formation_id("formation@name")
        
        with pytest.raises(ValueError, match="too long"):
            SchedulerInputValidator.validate_formation_id("a" * 256)
    
    def test_validate_title(self):
        """Test title validation."""
        # Valid titles
        valid_titles = [
            "Daily Report Generation",
            "Weekly Data Backup",
            "Monthly Summary Report",
            "Hourly Health Check",
        ]
        
        for title in valid_titles:
            SchedulerInputValidator.validate_title(title)
        
        # Invalid titles
        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerInputValidator.validate_title("")
        
        with pytest.raises(ValueError, match="too long"):
            SchedulerInputValidator.validate_title("a" * 501)
        
        with pytest.raises(ValueError, match="dangerous content"):
            SchedulerInputValidator.validate_title("Report ```bash rm -rf /```")
        
        with pytest.raises(ValueError, match="dangerous content"):
            SchedulerInputValidator.validate_title("Task <script>alert('xss')</script>")
    
    def test_validate_prompt(self):
        """Test prompt validation."""
        # Valid prompts
        valid_prompts = [
            "Generate a daily report",
            "Create a summary of recent activities",
            "Backup important data",
            "Send notification to team",
        ]
        
        for prompt in valid_prompts:
            SchedulerInputValidator.validate_prompt(prompt, "test_prompt")
        
        # Invalid prompts
        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerInputValidator.validate_prompt("", "test_prompt")
        
        with pytest.raises(ValueError, match="too long"):
            SchedulerInputValidator.validate_prompt("a" * 10001, "test_prompt")
        
        dangerous_prompts = [
            "exec('rm -rf /')",
            "eval('dangerous code')",
            "__import__('os').system('hack')",
            "subprocess.call(['rm', '-rf', '/'])",
            "system('malicious command')",
            "shell=True",
        ]
        
        for dangerous_prompt in dangerous_prompts:
            with pytest.raises(ValueError, match="dangerous content"):
                SchedulerInputValidator.validate_prompt(dangerous_prompt, "test_prompt")
    
    def test_validate_cron_expression(self):
        """Test cron expression validation."""
        # Valid cron expressions
        valid_crons = [
            "0 9 * * *",
            "*/15 * * * *",
            "0 0 1 * *",
            "0 12 * * 1-5",
            "30 14 * * 6,0",
        ]
        
        for cron_expr in valid_crons:
            SchedulerInputValidator.validate_cron_expression(cron_expr)
        
        # Invalid cron expressions
        invalid_crons = [
            "",
            None,
            123,
            "invalid cron",
            "0 9 * *",  # Too few fields
            "0 9 * * * *",  # Too many fields
            "a b c d e",  # Non-numeric
            "0" * 101,  # Too long
        ]
        
        for invalid_cron in invalid_crons:
            with pytest.raises(ValueError):
                SchedulerInputValidator.validate_cron_expression(invalid_cron)
    
    def test_validate_job_creation_comprehensive(self):
        """Test comprehensive job creation validation."""
        # Valid recurring job
        SchedulerInputValidator.validate_job_creation(
            user_id="test_user",
            formation_id="test_formation",
            title="Test Job",
            original_prompt="Create a report",
            execution_prompt="Execute report creation",
            cron_expression="0 9 * * *",
            is_recurring=True
        )
        
        # Valid one-time job
        future_time = utc_now() + timedelta(hours=1)
        SchedulerInputValidator.validate_job_creation(
            user_id="test_user",
            formation_id="test_formation",
            title="Test Job",
            original_prompt="Create a report",
            execution_prompt="Execute report creation",
            scheduled_for=future_time,
            is_recurring=False
        )
        
        # Invalid: recurring job without cron expression
        with pytest.raises(ValueError, match="require a cron_expression"):
            SchedulerInputValidator.validate_job_creation(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="test",
                execution_prompt="test",
                is_recurring=True
            )
        
        # Invalid: one-time job without scheduled_for
        with pytest.raises(ValueError, match="require a scheduled_for"):
            SchedulerInputValidator.validate_job_creation(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="test",
                execution_prompt="test",
                is_recurring=False
            )
        
        # Invalid: recurring job with scheduled_for
        with pytest.raises(ValueError, match="should not have scheduled_for"):
            SchedulerInputValidator.validate_job_creation(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="test",
                execution_prompt="test",
                cron_expression="0 9 * * *",
                scheduled_for=future_time,
                is_recurring=True
            )
        
        # Invalid: one-time job with cron_expression
        with pytest.raises(ValueError, match="should not have cron_expression"):
            SchedulerInputValidator.validate_job_creation(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="test",
                execution_prompt="test",
                cron_expression="0 9 * * *",
                scheduled_for=future_time,
                is_recurring=False
            )
        
        # Invalid: scheduled_for in the past
        past_time = utc_now() - timedelta(hours=1)
        with pytest.raises(ValueError, match="must be in the future"):
            SchedulerInputValidator.validate_job_creation(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="test",
                execution_prompt="test",
                scheduled_for=past_time,
                is_recurring=False
            )


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestRateLimiter:
    """Test the RateLimiter class."""
    
    def test_rate_limiter_basic_functionality(self):
        """Test basic rate limiting."""
        limiter = RateLimiter()
        limits = ResourceLimits(
            max_job_creations_per_hour=2,
            max_job_creations_per_day=5
        )
        
        # First request should succeed
        limiter.check_rate_limit("test_user", limits)
        
        # Second request should succeed
        limiter.check_rate_limit("test_user", limits)
        
        # Third request should fail (hourly limit)
        with pytest.raises(ValueError, match="Rate limit exceeded.*hour"):
            limiter.check_rate_limit("test_user", limits)
    
    def test_rate_limiter_different_users(self):
        """Test that rate limiting is per-user."""
        limiter = RateLimiter()
        limits = ResourceLimits(max_job_creations_per_hour=1)
        
        # Each user gets their own limit
        limiter.check_rate_limit("user1", limits)
        limiter.check_rate_limit("user2", limits)  # Should succeed
        
        # But each user is limited individually
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            limiter.check_rate_limit("user1", limits)
        
        # User2 can still make another request if within daily limit
        # (assuming daily limit > hourly limit for this test)
    
    def test_rate_limiter_cleanup(self):
        """Test that old entries are cleaned up."""
        limiter = RateLimiter()
        
        # Verify cleanup doesn't break functionality
        for i in range(5):
            limiter._cleanup_old_entries()
        
        # Should still work after cleanup
        limits = ResourceLimits(max_job_creations_per_hour=1)
        limiter.check_rate_limit("test_user", limits)


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestResourceLimits:
    """Test the ResourceLimits class."""
    
    def test_resource_limits_defaults(self):
        """Test default resource limits."""
        limits = ResourceLimits()
        
        assert limits.max_jobs_per_user == 100
        assert limits.max_concurrent_jobs_per_user == 5
        assert limits.max_execution_time_seconds == 300
        assert limits.max_job_creations_per_hour == 20
        assert limits.max_job_creations_per_day == 100
        assert limits.max_total_active_jobs == 10000
        assert limits.max_failed_executions_before_pause == 5
    
    def test_resource_limits_custom(self):
        """Test custom resource limits."""
        limits = ResourceLimits(
            max_jobs_per_user=50,
            max_concurrent_jobs_per_user=3,
            max_execution_time_seconds=600,
            max_job_creations_per_hour=10,
            max_job_creations_per_day=50,
            max_total_active_jobs=5000,
            max_failed_executions_before_pause=3
        )
        
        assert limits.max_jobs_per_user == 50
        assert limits.max_concurrent_jobs_per_user == 3
        assert limits.max_execution_time_seconds == 600
        assert limits.max_job_creations_per_hour == 10
        assert limits.max_job_creations_per_day == 50
        assert limits.max_total_active_jobs == 5000
        assert limits.max_failed_executions_before_pause == 3


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestSchedulerLimitsEnforcer:
    """Test the SchedulerLimitsEnforcer class."""
    
    @pytest.mark.asyncio
    async def test_check_job_creation_limits(self):
        """Test job creation limits checking."""
        limits = ResourceLimits(
            max_jobs_per_user=2,
            max_job_creations_per_hour=3
        )
        enforcer = SchedulerLimitsEnforcer(limits)
        
        # Mock job manager
        mock_job_manager = Mock()
        mock_job_manager.get_user_jobs.return_value = [
            {"status": "ACTIVE", "last_execution_status": "SUCCESS"},
        ]
        
        # Should pass with 1 active job (under limit of 2)
        await enforcer.check_job_creation_limits(mock_job_manager, "test_user")
        
        # Mock hitting the limit
        mock_job_manager.get_user_jobs.return_value = [
            {"status": "ACTIVE", "last_execution_status": "SUCCESS"},
            {"status": "ACTIVE", "last_execution_status": "SUCCESS"},
        ]
        
        # Should fail with 2 active jobs (at limit)
        with pytest.raises(ValueError, match="maximum job limit"):
            await enforcer.check_job_creation_limits(mock_job_manager, "test_user")
    
    @pytest.mark.asyncio
    async def test_check_system_limits(self):
        """Test system-wide limits checking."""
        limits = ResourceLimits(max_total_active_jobs=3)
        enforcer = SchedulerLimitsEnforcer(limits)
        
        # Mock job manager
        mock_job_manager = Mock()
        mock_job_manager.get_active_jobs.return_value = [
            {"id": "job1"}, {"id": "job2"}
        ]
        
        # Should pass with 2 jobs (under limit of 3)
        await enforcer.check_system_limits(mock_job_manager)
        
        # Mock hitting system limit
        mock_job_manager.get_active_jobs.return_value = [
            {"id": "job1"}, {"id": "job2"}, {"id": "job3"}
        ]
        
        # Should fail with 3 jobs (at limit)
        with pytest.raises(ValueError, match="maximum active job limit"):
            await enforcer.check_system_limits(mock_job_manager)
    
    def test_should_pause_job(self):
        """Test job pausing logic."""
        limits = ResourceLimits(max_failed_executions_before_pause=3)
        enforcer = SchedulerLimitsEnforcer(limits)
        
        # Job with few failures should not be paused
        job_few_failures = {"consecutive_failures": 2}
        assert not enforcer.should_pause_job(job_few_failures)
        
        # Job with many failures should be paused
        job_many_failures = {"consecutive_failures": 3}
        assert enforcer.should_pause_job(job_many_failures)
        
        # Job without failure count should not be paused
        job_no_failures = {}
        assert not enforcer.should_pause_job(job_no_failures)
    
    def test_get_execution_timeout(self):
        """Test execution timeout getter."""
        limits = ResourceLimits(max_execution_time_seconds=600)
        enforcer = SchedulerLimitsEnforcer(limits)
        
        assert enforcer.get_execution_timeout() == 600


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestGlobalLimitsConfiguration:
    """Test global limits configuration."""
    
    def test_get_limits_enforcer_singleton(self):
        """Test that get_limits_enforcer returns a singleton."""
        enforcer1 = get_limits_enforcer()
        enforcer2 = get_limits_enforcer()
        
        assert enforcer1 is enforcer2
    
    def test_configure_limits(self):
        """Test global limits configuration."""
        custom_limits = ResourceLimits(
            max_jobs_per_user=25,
            max_execution_time_seconds=120
        )
        
        configure_limits(custom_limits)
        enforcer = get_limits_enforcer()
        
        assert enforcer.limits.max_jobs_per_user == 25
        assert enforcer.limits.max_execution_time_seconds == 120


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import scheduler modules")
class TestUserAccessValidation:
    """Test user access validation."""
    
    def test_validate_user_access_valid(self):
        """Test valid user access."""
        # Should not raise for valid IDs
        validate_user_access("valid_user", "valid_formation")
    
    def test_validate_user_access_invalid_user(self):
        """Test invalid user ID."""
        with pytest.raises(ValueError, match="invalid characters"):
            validate_user_access("invalid@user", "valid_formation")
    
    def test_validate_user_access_invalid_formation(self):
        """Test invalid formation ID."""
        with pytest.raises(ValueError, match="invalid characters"):
            validate_user_access("valid_user", "invalid@formation")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])