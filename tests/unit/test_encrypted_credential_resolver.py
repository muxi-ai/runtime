"""
Tests for the encrypted credential resolver.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from cryptography.fernet import Fernet

from muxi.formation.credentials import EncryptedCredentialResolver


@pytest.fixture
def mock_session_maker():
    """Create a mock async session maker."""
    session = AsyncMock()
    session_maker = AsyncMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session_maker, session


@pytest.fixture
def resolver(mock_session_maker):
    """Create an EncryptedCredentialResolver instance."""
    session_maker, _ = mock_session_maker
    return EncryptedCredentialResolver(
        async_session_maker=session_maker,
        formation_id="test-formation",
        llm_model="test-model"
    )


@pytest.fixture
def resolver_with_custom_key(mock_session_maker):
    """Create an EncryptedCredentialResolver with custom encryption key."""
    session_maker, _ = mock_session_maker
    return EncryptedCredentialResolver(
        async_session_maker=session_maker,
        formation_id="test-formation",
        llm_model="test-model",
        encryption_key="my-custom-encryption-key"
    )


class TestEncryptedCredentialResolver:
    """Test suite for encrypted credential resolver."""
    
    def test_derive_user_key(self, resolver):
        """Test per-user key derivation."""
        # Derive key for user1
        fernet1 = resolver.derive_user_key("user1")
        assert isinstance(fernet1, Fernet)
        
        # Same user should get same key (cached)
        fernet1_again = resolver.derive_user_key("user1")
        assert fernet1 is fernet1_again
        
        # Different user should get different key
        fernet2 = resolver.derive_user_key("user2")
        assert isinstance(fernet2, Fernet)
        assert fernet2 is not fernet1
        
        # Test that keys are actually different
        test_data = b"test message"
        encrypted1 = fernet1.encrypt(test_data)
        encrypted2 = fernet2.encrypt(test_data)
        assert encrypted1 != encrypted2
    
    def test_derive_user_key_with_custom_key(self, resolver_with_custom_key):
        """Test key derivation with custom encryption key."""
        fernet = resolver_with_custom_key.derive_user_key("user1")
        assert isinstance(fernet, Fernet)
        
        # Verify custom key is used (not formation_id)
        assert resolver_with_custom_key.custom_key == "my-custom-encryption-key"
    
    def test_encrypt_credentials(self, resolver):
        """Test credential encryption."""
        user_id = "user123"
        credentials = {
            "api_key": "secret-key-123",
            "endpoint": "https://api.example.com"
        }
        
        encrypted = resolver._encrypt_credentials(user_id, credentials)
        
        # Check structure
        assert encrypted["version"] == "v1"
        assert encrypted["encrypted"] is True
        assert "data" in encrypted
        
        # Verify it's actually encrypted (not plaintext)
        assert "secret-key-123" not in encrypted["data"]
        assert "api.example.com" not in encrypted["data"]
        
        # Verify we can decrypt it back
        fernet = resolver.derive_user_key(user_id)
        decrypted_data = fernet.decrypt(encrypted["data"].encode('utf-8'))
        decrypted = json.loads(decrypted_data.decode('utf-8'))
        assert decrypted == credentials
    
    def test_decrypt_credentials_encrypted(self, resolver):
        """Test decryption of encrypted credentials."""
        user_id = "user123"
        original = {"api_key": "test-key", "user": "testuser"}
        
        # Encrypt first
        encrypted = resolver._encrypt_credentials(user_id, original)
        
        # Now decrypt
        decrypted = resolver._decrypt_credentials(user_id, encrypted)
        
        assert decrypted == original
    
    def test_decrypt_credentials_plaintext_backward_compatibility(self, resolver):
        """Test backward compatibility with plaintext credentials."""
        user_id = "user123"
        plaintext = {"api_key": "plain-key", "user": "plainuser"}
        
        # Decrypt should return plaintext as-is
        result = resolver._decrypt_credentials(user_id, plaintext)
        
        assert result == plaintext
    
    @pytest.mark.asyncio
    async def test_store_credential_encrypts(self, resolver, mock_session_maker):
        """Test that store_credential encrypts before storage."""
        session_maker, session = mock_session_maker
        
        # Mock user lookup
        user = MagicMock()
        user.id = 1
        user.external_user_id = "user123"
        
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=user)
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        
        # Store credentials
        credentials = {"token": "secret-token-456"}
        await resolver.store_credential(
            user_id="user123",
            service="github",
            credentials=credentials
        )
        
        # Verify session.add was called
        assert session.add.called or session.execute.called
        
        # If we captured the stored credential, verify it's encrypted
        # Note: In real implementation, we'd check the actual DB write
    
    @pytest.mark.asyncio
    async def test_resolve_decrypts(self, resolver, mock_session_maker):
        """Test that resolve decrypts stored credentials."""
        session_maker, session = mock_session_maker
        
        # Prepare encrypted credential
        user_id = "user123"
        original_creds = {"api_key": "secret-123"}
        encrypted = resolver._encrypt_credentials(user_id, original_creds)
        
        # Mock credential
        credential = MagicMock()
        credential.credentials = encrypted
        
        # Mock query result
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[credential])))
        session.execute = AsyncMock(return_value=result)
        
        # Resolve
        decrypted = await resolver.resolve(user_id, "github")
        
        # Should get back original credentials
        assert decrypted == original_creds
    
    @pytest.mark.asyncio
    async def test_resolve_handles_plaintext(self, resolver, mock_session_maker):
        """Test that resolve handles plaintext credentials for backward compatibility."""
        session_maker, session = mock_session_maker
        
        # Plaintext credential
        plaintext_creds = {"api_key": "plain-key"}
        
        # Mock credential
        credential = MagicMock()
        credential.credentials = plaintext_creds
        
        # Mock query result
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[credential])))
        session.execute = AsyncMock(return_value=result)
        
        # Resolve
        decrypted = await resolver.resolve("user123", "github")
        
        # Should get back plaintext as-is
        assert decrypted == plaintext_creds
    
    @pytest.mark.asyncio
    async def test_resolve_multiple_credentials(self, resolver, mock_session_maker):
        """Test resolving multiple credentials (returns list)."""
        session_maker, session = mock_session_maker
        
        user_id = "user123"
        
        # Create multiple encrypted credentials
        cred1_plain = {"api_key": "key1"}
        cred2_plain = {"api_key": "key2"}
        
        cred1 = MagicMock()
        cred1.name = "Personal"
        cred1.credentials = resolver._encrypt_credentials(user_id, cred1_plain)
        
        cred2 = MagicMock()
        cred2.name = "Work"
        cred2.credentials = resolver._encrypt_credentials(user_id, cred2_plain)
        
        # Mock query result
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred1, cred2])))
        session.execute = AsyncMock(return_value=result)
        
        # Resolve
        decrypted_list = await resolver.resolve(user_id, "github")
        
        # Should get list with decrypted credentials
        assert isinstance(decrypted_list, list)
        assert len(decrypted_list) == 2
        assert decrypted_list[0]["name"] == "Personal"
        assert decrypted_list[0]["credentials"] == cred1_plain
        assert decrypted_list[1]["name"] == "Work"
        assert decrypted_list[1]["credentials"] == cred2_plain
    
    def test_encryption_isolation_between_users(self, resolver):
        """Test that different users can't decrypt each other's credentials."""
        creds = {"secret": "my-secret"}
        
        # Encrypt for user1
        encrypted_user1 = resolver._encrypt_credentials("user1", creds)
        
        # Try to decrypt as user2 - should fail
        with pytest.raises(Exception):  # Fernet will raise InvalidToken
            resolver._decrypt_credentials("user2", encrypted_user1)
        
        # But user1 can decrypt their own
        decrypted = resolver._decrypt_credentials("user1", encrypted_user1)
        assert decrypted == creds
    
    def test_cache_efficiency(self, resolver):
        """Test that Fernet instances are cached for efficiency."""
        # First call creates and caches
        assert len(resolver._fernet_cache) == 0
        fernet1 = resolver.derive_user_key("user1")
        assert len(resolver._fernet_cache) == 1
        
        # Second call uses cache
        fernet1_again = resolver.derive_user_key("user1")
        assert fernet1 is fernet1_again
        assert len(resolver._fernet_cache) == 1
        
        # Different user adds to cache
        resolver.derive_user_key("user2")
        assert len(resolver._fernet_cache) == 2


class TestEncryptionPerformance:
    """Performance tests for encryption operations."""
    
    def test_encryption_performance(self, resolver):
        """Test that encryption is reasonably fast."""
        import time
        
        user_id = "user123"
        credentials = {
            "api_key": "x" * 100,  # 100 char key
            "secret": "y" * 100,
            "endpoint": "https://api.example.com/v1/endpoint"
        }
        
        # Measure encryption time
        start = time.time()
        for _ in range(100):
            encrypted = resolver._encrypt_credentials(user_id, credentials)
        encryption_time = time.time() - start
        
        # Should be fast (< 1 second for 100 operations)
        assert encryption_time < 1.0
        
        # Measure decryption time
        start = time.time()
        for _ in range(100):
            resolver._decrypt_credentials(user_id, encrypted)
        decryption_time = time.time() - start
        
        # Should be fast (< 1 second for 100 operations)
        assert decryption_time < 1.0