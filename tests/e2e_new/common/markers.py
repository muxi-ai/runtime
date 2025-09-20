"""
Test categorization markers for different test types and requirements.
"""

import pytest
# Test priority markers
smoke = pytest.mark.smoke  # Quick tests for PR validation (~5 min)
regression = pytest.mark.regression  # Full regression suite (~45 min)
critical = pytest.mark.critical  # Must-pass tests
extended = pytest.mark.extended  # Extended tests (optional)

# Test speed markers
fast = pytest.mark.fast  # <5 seconds
slow = pytest.mark.slow  # >30 seconds
very_slow = pytest.mark.very_slow  # >2 minutes

# Dependency markers
requires_postgres = pytest.mark.requires_postgres
requires_faissx = pytest.mark.requires_faissx
requires_webhook = pytest.mark.requires_webhook
requires_a2a = pytest.mark.requires_a2a
requires_gpu = pytest.mark.requires_gpu  # For multimodal tests

# Parallelization markers
serial = pytest.mark.serial  # Must run sequentially
parallel_safe = pytest.mark.parallel_safe  # Safe to run in parallel
rate_limited = pytest.mark.rate_limited  # Has API rate limits
# Feature coverage markers
def covers(*features):
    """Mark test as covering specific features."""
    return pytest.mark.covers(features=features)
