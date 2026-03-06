"""Test InitEventFormatter and InitFailureInfo."""


from muxi.runtime.datatypes.observability import InitEventFormatter, InitFailureInfo


def test_format_ok_basic():
    """Test basic OK formatting."""
    result = InitEventFormatter.format_ok("MCP server: filesystem")
    assert "[  OK  ]" in result
    assert "MCP server: filesystem" in result


def test_format_ok_with_details():
    """Test OK formatting with details."""
    result = InitEventFormatter.format_ok("MCP server: filesystem", "3 tools")
    assert "[  OK  ]" in result
    assert "MCP server: filesystem (3 tools)" in result


def test_format_warn_basic():
    """Test basic WARN formatting."""
    result = InitEventFormatter.format_warn("Vector memory: disabled")
    assert "[ WARN ]" in result
    assert "Vector memory: disabled" in result


def test_format_warn_with_details():
    """Test WARN formatting with details."""
    result = InitEventFormatter.format_warn("Database: using SQLite", "PostgreSQL unavailable")
    assert "[ WARN ]" in result
    assert "Database: using SQLite (PostgreSQL unavailable)" in result


def test_format_info_basic():
    """Test basic INFO formatting."""
    result = InitEventFormatter.format_info("Buffer memory: FIFO mode")
    assert "[ INFO ]" in result
    assert "Buffer memory: FIFO mode" in result


def test_format_info_with_details():
    """Test INFO formatting with details."""
    result = InitEventFormatter.format_info("Buffer memory: FIFO mode", "100 messages")
    assert "[ INFO ]" in result
    assert "Buffer memory: FIFO mode (100 messages)" in result


def test_format_fail_complete():
    """Test complete failure formatting with all fields."""
    failure_info = InitFailureInfo(
        component="MCP server: filesystem",
        problem="Connection timeout after 5 seconds",
        context="formation.afs:45 (mcp.servers.filesystem)",
        causes=[
            "Server executable not installed or not in PATH",
            "Incorrect command in formation config",
            "Server crashed on launch",
        ],
        fixes=[
            "Test manually: npx @modelcontextprotocol/server-filesystem",
            "Install if needed: npm install -g @modelcontextprotocol/server-filesystem",
            "Check formation.afs → mcp.servers.filesystem.command",
        ],
        technical='Traceback (most recent call last):\n  File "test.py", line 1\nTimeoutError: Server did not respond',
    )

    result = InitEventFormatter.format_fail(failure_info)

    # Verify all components are present
    assert "[ FAIL ]" in result
    assert "MCP server: filesystem" in result
    assert "Connection timeout after 5 seconds" in result
    assert "Common causes:" in result
    assert "Server executable not installed" in result
    assert "To fix:" in result
    assert "Test manually:" in result
    assert "Config: formation.afs:45" in result
    assert "TimeoutError: Server did not respond" in result


def test_format_fail_minimal():
    """Test failure formatting with minimal fields."""
    failure_info = InitFailureInfo(
        component="Database",
        problem="Connection refused",
        context="formation.afs:12 (database.connection)",
        causes=[],
        fixes=[],
        technical="ConnectionError: Could not connect",
    )

    result = InitEventFormatter.format_fail(failure_info)

    # Verify minimal components are present
    assert "[ FAIL ]" in result
    assert "Database" in result
    assert "Connection refused" in result
    assert "Config: formation.afs:12" in result
    assert "ConnectionError: Could not connect" in result

    # Verify optional sections are not present when empty
    assert "Common causes:" not in result
    assert "To fix:" not in result


def test_format_summary():
    """Test startup summary formatting."""
    result = InitEventFormatter.format_summary(2.3, 8, 1, 0)
    assert "Startup completed in 2.3s" in result
    assert "8 services" in result
    assert "1 warning" in result  # singular
    assert "0 errors" in result


def test_format_summary_plural():
    """Test startup summary with plural warnings/errors."""
    result = InitEventFormatter.format_summary(5.7, 12, 3, 2)
    assert "Startup completed in 5.7s" in result
    assert "12 services" in result
    assert "3 warnings" in result  # plural
    assert "2 errors" in result  # plural


def test_format_summary_no_issues():
    """Test startup summary with no warnings or errors."""
    result = InitEventFormatter.format_summary(1.5, 5, 0, 0)
    assert "Startup completed in 1.5s" in result
    assert "5 services" in result
    assert "0 warnings" in result
    assert "0 errors" in result
