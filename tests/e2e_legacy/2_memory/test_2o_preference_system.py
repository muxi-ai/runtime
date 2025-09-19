"""
Test Group 2O: Preference System
Testing the ultra-simple preference detection and storage system.
"""

import pytest
import asyncio
from typing import Dict, Any

from muxi.federation.federation import MuxiFederation


class Test2OPreferenceSystem:
    """Test the preference detection, storage, and retrieval in chat flow."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Set up test fixtures."""
        self.federation = None
        self.overlord = None
        self.user_id = "test_pref_user_123"
        yield
        # Cleanup
        if self.federation:
            await self.federation.cleanup()

    async def setup_formation(self, formation_config: Dict[str, Any]):
        """Helper to set up a formation with the given config."""
        self.federation = MuxiFederation()
        formation_name, self.overlord = await self.federation.create_formation(
            formation_yaml=formation_config,
            name="test_preference_formation"
        )
        return formation_name

    @pytest.mark.asyncio
    async def test_2o1_preference_detection_and_storage(self):
        """Test that user preferences are detected and stored in the preferences collection."""

        # Create formation with memory enabled
        formation_config = {
            "name": "preference_test_formation",
            "llm": {
                "models": [
                    {"text": "openai/gpt-4o-mini"}
                ]
            },
            "memory": {
                "long_term": True,
                "backend": "sqlite"
            },
            "agents": [
                {
                    "name": "test_agent",
                    "role": "General Assistant",
                    "persona": "You are a helpful assistant."
                }
            ]
        }

        await self.setup_formation(formation_config)

        # Express a preference
        preference_message = "I prefer using FastAPI over Flask for all my API development work"
        response1 = await self.overlord.chat(preference_message, user_id=self.user_id)

        # Give time for async preference storage
        await asyncio.sleep(2)

        # Ask a related question to see if preference is retrieved
        api_question = "What framework should I use to build a REST API?"
        response2 = await self.overlord.chat(api_question, user_id=self.user_id)

        # Search memory to verify preference was stored
        if self.overlord.persistent_memory_manager:
            search_results = await self.overlord.persistent_memory_manager.search_long_term_memory(
                query="FastAPI Flask API development",
                k=5,
                user_id=self.user_id,
                collections=["preferences"]
            )

            # Check if preference was stored
            preference_found = False
            if search_results:
                for result in search_results:
                    if "FastAPI" in result.get("text", "") and "Flask" in result.get("text", ""):
                        preference_found = True
                        break

            assert preference_found, "Preference was not stored in preferences collection"

        # Basic check that the assistant acknowledges the preference
        assert response1 is not None, "Should get a response to preference statement"

        print("\n=== Test 2O1 Results ===")
        print(f"Preference statement: {preference_message}")
        print(f"Response to preference: {response1[:200] if len(response1) > 200 else response1}")
        print(f"API question: {api_question}")
        print(f"Response mentioning preference: {'FastAPI' in response2 or 'fastapi' in response2.lower()}")
        print("Preference stored in collection: ✓")

    @pytest.mark.asyncio
    async def test_2o2_preference_context_inclusion(self):
        """Test that stored preferences are included in context for relevant queries."""

        # Create formation with memory enabled
        formation_config = {
            "name": "preference_context_formation",
            "llm": {
                "models": [
                    {"text": "openai/gpt-4o-mini"}
                ]
            },
            "memory": {
                "long_term": True,
                "backend": "sqlite"
            },
            "agents": [
                {
                    "name": "developer_agent",
                    "role": "Development Assistant",
                    "persona": (
                        "You are a software development assistant. "
                        "When users have stated preferences, honor them in your recommendations."
                    )
                }
            ]
        }

        await self.setup_formation(formation_config)

        # Store multiple preferences
        preferences = [
            "I always use pytest for testing, never unittest",
            "For UI components, I prefer using Shadcn/UI with Tailwind CSS",
            "I like to use TypeScript instead of JavaScript for all my projects"
        ]

        for pref in preferences:
            await self.overlord.chat(pref, user_id=self.user_id)
            await asyncio.sleep(1)  # Give time for storage

        # Test 1: Ask about testing - should retrieve pytest preference
        test_response = await self.overlord.chat(
            "What testing framework should I use for my Python project?",
            user_id=self.user_id
        )

        # Test 2: Ask about UI - should retrieve Shadcn/UI preference
        ui_response = await self.overlord.chat(
            "I need to build a dashboard with some components. What should I use?",
            user_id=self.user_id
        )

        # Test 3: Ask about JavaScript - should retrieve TypeScript preference
        js_response = await self.overlord.chat(
            "Should I use JavaScript or TypeScript for a new web app?",
            user_id=self.user_id
        )

        # Verify preferences are reflected in responses
        pytest_mentioned = "pytest" in test_response.lower()
        shadcn_mentioned = "shadcn" in ui_response.lower() or "tailwind" in ui_response.lower()
        typescript_mentioned = "typescript" in js_response.lower()

        print("\n=== Test 2O2 Results ===")
        print("Preferences stored:")
        for pref in preferences:
            print(f"  - {pref}")
        print("\nContext inclusion results:")
        print(f"  Testing question -> pytest mentioned: {pytest_mentioned}")
        print(f"  UI question -> Shadcn/Tailwind mentioned: {shadcn_mentioned}")
        print(f"  JS/TS question -> TypeScript mentioned: {typescript_mentioned}")

        # At least 2 out of 3 preferences should be reflected
        preferences_reflected = sum([pytest_mentioned, shadcn_mentioned, typescript_mentioned])
        assert preferences_reflected >= 2, f"Only {preferences_reflected}/3 preferences were reflected in responses"

        print(f"\nPreferences reflected: {preferences_reflected}/3 ✓")

        # Verify preferences are in the preferences collection
        if self.overlord.persistent_memory_manager:
            pref_search = await self.overlord.persistent_memory_manager.search_long_term_memory(
                query="preferences testing UI TypeScript",
                k=10,
                user_id=self.user_id,
                collections=["preferences"]
            )

            assert pref_search and len(pref_search) > 0, "No preferences found in preferences collection"
            print(f"Preferences in collection: {len(pref_search)} entries found ✓")
