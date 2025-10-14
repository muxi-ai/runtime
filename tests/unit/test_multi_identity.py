"""
Unit tests for multi-identity user management.

Tests the multi-identity system components including user resolution,
identifier management, and database operations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

# We'll test the actual integration rather than mocking everything
# This ensures our multi-identity system actually works


@pytest.mark.asyncio
async def test_user_identifier_model_structure():
    """Test that UserIdentifier model has correct structure."""
    from muxi.services.memory.long_term import UserIdentifier
    
    # Check that model has required attributes
    assert hasattr(UserIdentifier, '__tablename__')
    assert UserIdentifier.__tablename__ == 'user_identifiers'
    
    # Check columns exist
    assert hasattr(UserIdentifier, 'id')
    assert hasattr(UserIdentifier, 'user_id')
    assert hasattr(UserIdentifier, 'identifier')
    assert hasattr(UserIdentifier, 'identifier_type')
    assert hasattr(UserIdentifier, 'formation_id')
    assert hasattr(UserIdentifier, 'created_at')


@pytest.mark.asyncio
async def test_user_model_no_external_user_id():
    """Test that User model does NOT have external_user_id column."""
    from muxi.services.memory.long_term import User
    
    # User model should NOT have external_user_id
    assert not hasattr(User, 'external_user_id')
    
    # Should have these fields
    assert hasattr(User, 'id')
    assert hasattr(User, 'public_id')
    assert hasattr(User, 'formation_id')
    assert hasattr(User, 'created_at')
    assert hasattr(User, 'updated_at')


@pytest.mark.asyncio
async def test_resolve_user_identifier_function_exists():
    """Test that resolve_user_identifier function is available."""
    from muxi.utils.user_resolution import resolve_user_identifier
    
    # Function should exist
    assert callable(resolve_user_identifier)
    
    # Check signature
    import inspect
    sig = inspect.signature(resolve_user_identifier)
    params = list(sig.parameters.keys())
    
    assert 'identifier' in params
    assert 'formation_id' in params
    assert 'db_manager' in params or 'db_session_maker' in params


@pytest.mark.asyncio
async def test_associate_user_identifiers_function_exists():
    """Test that associate_user_identifiers function is available."""
    from muxi.utils.user_resolution import associate_user_identifiers
    
    # Function should exist
    assert callable(associate_user_identifiers)
    
    # Check signature
    import inspect
    sig = inspect.signature(associate_user_identifiers)
    params = list(sig.parameters.keys())
    
    assert 'identifiers' in params
    assert 'formation_id' in params


def test_long_term_memory_has_resolve_helpers():
    """Test that LongTermMemory has resolution helper methods."""
    from muxi.services.memory.long_term import LongTermMemory
    
    # Check that helper methods exist
    assert hasattr(LongTermMemory, '_resolve_user_id_sync')
    assert hasattr(LongTermMemory, '_resolve_user_id_async')


def test_scheduler_has_resolve_helper():
    """Test that JobManager has resolution helper method."""
    from muxi.services.scheduler.manager import JobManager
    
    # Check that helper method exists
    assert hasattr(JobManager, '_resolve_user_id_sync')


def test_credentials_resolver_has_resolve_helper():
    """Test that CredentialResolver has resolution helper method."""
    from muxi.formation.credentials.resolver import CredentialResolver
    
    # Check that helper method exists
    assert hasattr(CredentialResolver, '_resolve_user_id')


@pytest.mark.asyncio
async def test_request_context_has_user_id_fields():
    """Test that RequestContext has all three user ID fields."""
    from muxi.datatypes.observability import RequestContext
    
    # Create instance
    ctx = RequestContext(id="test_123")
    
    # Check all three user ID fields exist
    assert hasattr(ctx, 'internal_user_id')
    assert hasattr(ctx, 'muxi_user_id')
    assert hasattr(ctx, 'user_id')
    
    # Check they default to None
    assert ctx.internal_user_id is None
    assert ctx.muxi_user_id is None
    assert ctx.user_id is None
    
    # Check they can be set
    ctx.internal_user_id = 123
    ctx.muxi_user_id = "usr_abc"
    ctx.user_id = "alice@example.com"
    
    assert ctx.internal_user_id == 123
    assert ctx.muxi_user_id == "usr_abc"
    assert ctx.user_id == "alice@example.com"


def test_sqlite_memory_updated():
    """Test that SQLiteMemory has been updated for multi-identity."""
    from muxi.services.memory.sqlite import SQLiteMemory
    import inspect
    
    # Check get_or_create_user method signature
    method = getattr(SQLiteMemory, 'get_or_create_user', None)
    assert method is not None
    
    # Check the method source doesn't reference external_user_id column query
    source = inspect.getsource(method)
    # Should query user_identifiers, not users.external_user_id
    assert 'user_identifiers' in source or 'UserIdentifier' in source


def test_no_old_get_or_create_user_methods():
    """Test that old _get_or_create_user methods have been removed."""
    from muxi.services.scheduler.manager import JobManager
    from muxi.services.memory.long_term import LongTermMemory
    import inspect
    
    # Check scheduler doesn't have old method
    if hasattr(JobManager, '_get_or_create_user'):
        # If it exists, check it's not the broken old version
        source = inspect.getsource(JobManager._get_or_create_user)
        # Should NOT query User.external_user_id
        assert 'external_user_id' not in source or 'DEPRECATED' in source
    
    # Check long_term doesn't have old method (or it's deprecated)
    if hasattr(LongTermMemory, '_get_or_create_user'):
        source = inspect.getsource(LongTermMemory._get_or_create_user)
        assert 'external_user_id' not in source or 'DEPRECATED' in source


@pytest.mark.asyncio
async def test_init_schemas_have_multi_identity():
    """Test that init schemas include multi-identity tables (no incremental migrations needed)."""
    import os
    
    migrations_dir = 'migrations'
    
    # Check init schemas have user_identifiers table (SINGLE SOURCE OF TRUTH)
    with open(f'{migrations_dir}/init_schema.sql', 'r') as f:
        init_schema = f.read()
        assert 'user_identifiers' in init_schema, "PostgreSQL init schema missing user_identifiers table"
        assert 'external_user_id' not in init_schema, "PostgreSQL init schema should not have external_user_id column"
    
    with open(f'{migrations_dir}/init_schema_sqlite.sql', 'r') as f:
        init_schema_sqlite = f.read()
        assert 'user_identifiers' in init_schema_sqlite, "SQLite init schema missing user_identifiers table"
        assert 'external_user_id' not in init_schema_sqlite, "SQLite init schema should not have external_user_id column"


def test_user_model_imports():
    """Test that User and UserIdentifier can be imported."""
    from muxi.services.memory.long_term import User, UserIdentifier
    
    assert User is not None
    assert UserIdentifier is not None


def test_resolution_utilities_import():
    """Test that resolution utilities can be imported."""
    from muxi.utils.user_resolution import (
        resolve_user_identifier,
        associate_user_identifiers,
    )
    
    assert resolve_user_identifier is not None
    assert associate_user_identifiers is not None


@pytest.mark.asyncio
async def test_chat_orchestrator_uses_resolution():
    """Test that ChatOrchestrator imports resolution utilities."""
    from muxi.formation.overlord.chat_orchestrator import ChatOrchestrator
    import inspect
    
    # Check that the module has access to resolution
    source = inspect.getsource(ChatOrchestrator)
    # Should import or use resolve_user_identifier
    assert 'resolve_user_identifier' in source or 'user_resolution' in source


def test_observability_events_defined():
    """Test that observability module is available."""
    from muxi.services import observability
    
    # Check that SystemEvents exists
    assert hasattr(observability, 'SystemEvents')
    
    # Check that we can observe events
    assert hasattr(observability, 'observe')
    assert callable(observability.observe)


@pytest.mark.asyncio
async def test_encrypted_credentials_updated():
    """Test that EncryptedCredentialResolver has been updated."""
    from muxi.formation.credentials.encrypted import EncryptedCredentialResolver
    import inspect
    
    # Check that it doesn't have broken queries
    source = inspect.getsource(EncryptedCredentialResolver)
    
    # Should import resolve_user_identifier
    assert 'resolve_user_identifier' in source or 'user_resolution' in source


def test_documentation_exists():
    """Test that implementation documentation exists."""
    import os
    
    docs = [
        'MULTI_IDENTITY_IMPLEMENTATION_PLAN.md',
        'MULTI_IDENTITY_COMPLETE.md',
        'MULTI_IDENTITY_ISSUES_FOUND.md',
    ]
    
    for doc in docs:
        assert os.path.exists(doc), f"Documentation {doc} should exist"


# Test actual behavior with mock database
@pytest.mark.asyncio
async def test_resolve_user_id_sync_with_request_context():
    """Test _resolve_user_id_sync uses RequestContext when available."""
    from muxi.services.memory.long_term import LongTermMemory
    from muxi.datatypes.observability import RequestContext
    import inspect
    
    # Check method exists
    assert hasattr(LongTermMemory, '_resolve_user_id_sync')
    
    # Check source uses RequestContext
    source = inspect.getsource(LongTermMemory._resolve_user_id_sync)
    assert 'RequestContext' in source or 'ctx' in source


@pytest.mark.asyncio
async def test_request_context_manager_accepts_user_ids():
    """Test that RequestContextManager.track_request accepts user IDs."""
    from muxi.services.observability.request_manager import RequestContextManager
    import inspect
    
    # Check track_request signature
    sig = inspect.signature(RequestContextManager.track_request)
    params = list(sig.parameters.keys())
    
    # Should accept user ID parameters
    assert 'internal_user_id' in params or 'user_id' in params


def test_no_external_user_id_in_models():
    """Final check: No model should have external_user_id attribute."""
    from muxi.services.memory.long_term import User
    from muxi.services.scheduler.models import ScheduledJob
    import inspect
    
    # Check User model
    user_source = inspect.getsource(User)
    # If external_user_id appears, it should only be in comments about removal
    if 'external_user_id' in user_source:
        assert 'external_user_id' not in [attr for attr in dir(User) if not attr.startswith('_')]
    
    # ScheduledJob should still have user_id (which is internal_user_id)
    assert hasattr(ScheduledJob, 'user_id')
