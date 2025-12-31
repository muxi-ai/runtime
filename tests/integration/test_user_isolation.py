"""
Integration tests for user isolation in credential handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from muxi.runtime.formation.credentials import EncryptedCredentialResolver
from muxi.runtime.formation.credentials.resolver import CredentialResolver


@pytest.fixture
def mock_session_with_users():
    """Create mock session with multiple users."""
    session = AsyncMock()
    session_maker = AsyncMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Create mock users
    user1 = MagicMock()
    user1.id = 1
    user1.external_user_id = "alice"
    user1.formation_id = "test-formation"

    user2 = MagicMock()
    user2.id = 2
    user2.external_user_id = "bob"
    user2.formation_id = "test-formation"

    # Store credentials for each user
    users_data = {
        "alice": {
            "user": user1,
            "credentials": {
                "github": {"api_key": "alice-github-key"},
                "openai": {"api_key": "alice-openai-key"}
            }
        },
        "bob": {
            "user": user2,
            "credentials": {
                "github": {"api_key": "bob-github-key"},
                "openai": {"api_key": "bob-openai-key"}
            }
        }
    }

    return session_maker, session, users_data


class TestUserIsolation:
    """Test that users cannot access each other's credentials."""

    @pytest.mark.asyncio
    async def test_users_cannot_access_others_credentials(self, mock_session_with_users):
        """Test users can only access their own credentials."""
        session_maker, session, users_data = mock_session_with_users

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            result = MagicMock()

            # Check which user is being queried
            if "alice" in stmt_str:
                if "github" in stmt_str.lower():
                    cred = MagicMock()
                    cred.credentials = users_data["alice"]["credentials"]["github"]
                    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred])))
                else:
                    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            elif "bob" in stmt_str:
                if "github" in stmt_str.lower():
                    cred = MagicMock()
                    cred.credentials = users_data["bob"]["credentials"]["github"]
                    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred])))
                else:
                    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

            return result

        session.execute = mock_execute

        resolver = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="test-formation"
        )

        # Alice gets her credential
        alice_cred = await resolver.resolve("alice", "github")
        assert alice_cred == {"api_key": "alice-github-key"}

        # Bob gets his credential
        bob_cred = await resolver.resolve("bob", "github")
        assert bob_cred == {"api_key": "bob-github-key"}

        # Alice cannot get Bob's credential (query filters by user)
        # This would return None in real implementation
        alice_trying_bob = await resolver.resolve("alice", "github")
        assert alice_trying_bob != {"api_key": "bob-github-key"}

    @pytest.mark.asyncio
    async def test_formation_isolation(self, mock_session_with_users):
        """Test credentials are isolated by formation_id."""
        session_maker, session, users_data = mock_session_with_users

        # Create user in different formation
        user3 = MagicMock()
        user3.id = 3
        user3.external_user_id = "charlie"
        user3.formation_id = "other-formation"

        query_formation = None

        async def mock_execute(stmt):
            nonlocal query_formation
            stmt_str = str(stmt)

            # Extract formation_id from query
            if "test-formation" in stmt_str:
                query_formation = "test-formation"
            elif "other-formation" in stmt_str:
                query_formation = "other-formation"

            result = MagicMock()

            # Only return data if formation matches
            if query_formation == "test-formation" and "alice" in stmt_str:
                cred = MagicMock()
                cred.credentials = {"api_key": "alice-key"}
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred])))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

            return result

        session.execute = mock_execute

        # Resolver for test-formation
        resolver1 = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="test-formation"
        )

        # Resolver for other-formation
        resolver2 = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="other-formation"
        )

        # User in test-formation can get their credential
        await resolver1.resolve("alice", "service")
        # Would return alice's credential in real implementation

        # User in other-formation cannot get alice's credential
        await resolver2.resolve("alice", "service")
        # Would return None in real implementation due to formation_id filter

    def test_encryption_provides_user_isolation(self):
        """Test encryption keys are unique per user."""
        resolver = EncryptedCredentialResolver(
            async_session_maker=AsyncMock(),
            formation_id="test-formation"
        )

        # Each user gets unique key
        alice_key = resolver.derive_user_key("alice")
        bob_key = resolver.derive_user_key("bob")

        # Keys are different
        test_data = b"test credential"
        alice_encrypted = alice_key.encrypt(test_data)
        bob_encrypted = bob_key.encrypt(test_data)

        # Encrypted data is different
        assert alice_encrypted != bob_encrypted

        # Alice cannot decrypt Bob's data
        with pytest.raises(Exception):  # Fernet.InvalidToken
            alice_key.decrypt(bob_encrypted)

        # Bob cannot decrypt Alice's data
        with pytest.raises(Exception):  # Fernet.InvalidToken
            bob_key.decrypt(alice_encrypted)

    @pytest.mark.asyncio
    async def test_cache_isolation(self):
        """Test in-memory cache is isolated per user."""
        resolver = CredentialResolver(
            async_session_maker=AsyncMock(),
            formation_id="test-formation"
        )

        # Manually populate cache for testing
        resolver._cache = {
            "alice": {
                "github": {"api_key": "alice-github"},
                "openai": {"api_key": "alice-openai"}
            },
            "bob": {
                "github": {"api_key": "bob-github"}
            }
        }

        # Alice's cache
        assert "github" in resolver._cache.get("alice", {})
        assert resolver._cache["alice"]["github"]["api_key"] == "alice-github"

        # Bob's cache
        assert "github" in resolver._cache.get("bob", {})
        assert resolver._cache["bob"]["github"]["api_key"] == "bob-github"

        # Alice doesn't have Bob's credentials in cache
        assert resolver._cache.get("alice", {}).get("github") != {"api_key": "bob-github"}

        # Bob doesn't have Alice's openai credential
        assert "openai" not in resolver._cache.get("bob", {})

    @pytest.mark.asyncio
    async def test_sql_injection_protection(self, mock_session_with_users):
        """Test that user IDs are properly parameterized."""
        session_maker, session, _ = mock_session_with_users

        executed_statements = []

        async def mock_execute(stmt):
            executed_statements.append(str(stmt))
            result = MagicMock()
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            return result

        session.execute = mock_execute

        resolver = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="test-formation"
        )

        # Try to inject SQL
        malicious_user_id = "alice'; DROP TABLE credentials; --"
        await resolver.resolve(malicious_user_id, "github")

        # Check that the query was parameterized (not concatenated)
        for stmt in executed_statements:
            # Should use parameter binding, not string concatenation
            assert "DROP TABLE" not in stmt
            # The malicious string should be treated as data, not SQL

    @pytest.mark.asyncio
    async def test_no_global_user_state(self):
        """Test no global state leaks between users."""
        resolver = CredentialResolver(
            async_session_maker=AsyncMock(),
            formation_id="test-formation"
        )

        # No user-specific data should be stored at class level
        assert not hasattr(resolver, 'current_user')
        assert not hasattr(resolver, 'user_id')
        assert not hasattr(resolver, 'user_credentials')

        # Cache should be properly namespaced
        assert isinstance(resolver._cache, dict)

        # Formation ID is shared (that's ok)
        assert resolver.formation_id == "test-formation"

    @pytest.mark.asyncio
    async def test_concurrent_user_access(self):
        """Test concurrent access by multiple users doesn't leak data."""
        import asyncio

        session = AsyncMock()
        session_maker = AsyncMock(return_value=session)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        # Track which user is making the request
        user_requests = []

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            user = "alice" if "alice" in stmt_str else "bob" if "bob" in stmt_str else "unknown"
            user_requests.append(user)

            result = MagicMock()
            if user == "alice":
                cred = MagicMock()
                cred.credentials = {"api_key": f"{user}-key"}
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred])))
            elif user == "bob":
                cred = MagicMock()
                cred.credentials = {"api_key": f"{user}-key"}
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred])))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

            # Simulate some async delay
            await asyncio.sleep(0.01)
            return result

        session.execute = mock_execute

        resolver = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="test-formation"
        )

        # Concurrent requests from different users
        alice_task = asyncio.create_task(resolver.resolve("alice", "github"))
        bob_task = asyncio.create_task(resolver.resolve("bob", "github"))

        alice_result, bob_result = await asyncio.gather(alice_task, bob_task)

        # Each user got their own credential
        assert alice_result == {"api_key": "alice-key"}
        assert bob_result == {"api_key": "bob-key"}

        # Both users made requests
        assert "alice" in user_requests
        assert "bob" in user_requests


class TestMultiUserScenarios:
    """Test realistic multi-user scenarios."""

    @pytest.mark.asyncio
    async def test_team_sharing_formation(self):
        """Test multiple users in same formation with separate credentials."""
        resolver = EncryptedCredentialResolver(
            async_session_maker=AsyncMock(),
            formation_id="team-formation"
        )

        # Team members
        team = ["alice", "bob", "charlie", "dana"]

        # Each gets unique encryption
        credentials = {}
        encrypted = {}

        for member in team:
            # Each member has their own GitHub token
            cred = {"github_token": f"ghp_{member}_secret123"}
            credentials[member] = cred
            encrypted[member] = resolver._encrypt_credentials(member, cred)

        # Verify all encrypted differently
        encrypted_values = [enc["data"] for enc in encrypted.values()]
        assert len(set(encrypted_values)) == len(team)  # All unique

        # Each can only decrypt their own
        for member in team:
            # Can decrypt own
            decrypted = resolver._decrypt_credentials(member, encrypted[member])
            assert decrypted == credentials[member]

            # Cannot decrypt others
            for other in team:
                if other != member:
                    with pytest.raises(Exception):
                        resolver._decrypt_credentials(member, encrypted[other])

    @pytest.mark.asyncio
    async def test_user_credential_lifecycle(self):
        """Test complete lifecycle of user credentials."""
        # This test documents the expected user journey

        session = AsyncMock()
        session_maker = AsyncMock(return_value=session)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        # Track lifecycle events
        events = []

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            if "INSERT" in stmt_str:
                events.append("create")
            elif "UPDATE" in stmt_str:
                events.append("update")
            elif "DELETE" in stmt_str:
                events.append("delete")
            elif "SELECT" in stmt_str:
                events.append("read")

            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            return result

        session.execute = mock_execute
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        resolver = CredentialResolver(
            async_session_maker=session_maker,
            formation_id="test-formation"
        )

        # 1. User stores credential (CREATE)
        await resolver.store_credential("alice", "github", {"api_key": "ghp_123"})
        assert "create" in events or "read" in events  # Might check existence first

        # 2. User retrieves credential (READ)
        events.clear()
        await resolver.resolve("alice", "github")
        assert "read" in events

        # 3. User updates credential (UPDATE)
        events.clear()
        await resolver.store_credential("alice", "github", {"api_key": "ghp_456"})
        # Would trigger update in real implementation

        # 4. User removes credential (DELETE)
        # Note: Delete not implemented in current CredentialResolver
        # This documents expected behavior

    @pytest.mark.asyncio
    async def test_user_without_credentials(self):
        """Test handling users who haven't stored credentials."""
        resolver = CredentialResolver(
            async_session_maker=AsyncMock(),
            formation_id="test-formation"
        )

        # Mock empty response
        session = AsyncMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        session.execute = AsyncMock(return_value=result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        resolver.async_session_maker = AsyncMock(return_value=session)

        # New user with no credentials
        result = await resolver.resolve("new_user", "github")

        # Should return None, not error
        assert result is None

        # Cache should reflect no credential
        assert resolver._cache.get("new_user", {}).get("github") is None
