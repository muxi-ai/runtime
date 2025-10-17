# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Extractor - Automatic Information Extraction
# Description:  System for automatically extracting and storing user information
# Role:         Analyzes conversations to build persistent user context
# Usage:        Used by Overlord to maintain user knowledge over time
# Author:       Muxi Framework Team
#
# The Memory Extractor module provides an intelligent system for automatically
# extracting important information about users from conversations. It:
#
# 1. Conversation Analysis
#    - Processes user messages and agent responses
#    - Identifies key facts, preferences, and details about users
#    - Assigns confidence and importance scores to extracted information
#
# 2. Privacy-Focused Design
#    - Built-in sensitivity detection for PII and sensitive data
#    - Configurable opt-out/opt-in mechanisms
#    - User data purging capabilities
#    - Data retention policies
#
# 3. Intelligent Information Management
#    - Automatic conflict resolution with existing knowledge
#    - Timestamped information tracking
#    - Metadata for information provenance
#    - Confidence-based storage decisions
#
# This system enables agents to build context about users over time without
# explicit memory commands, creating a more natural and personalized experience.
# =============================================================================

import json
import time
from typing import Set, Any

from .. import observability


class MemoryExtractor:
    """
    A class for automatically extracting user information from conversations
    and storing it in context memory.

    The MemoryExtractor analyzes conversation history, identifies key facts
    about users, scores their importance and confidence, and updates the
    user's context memory. It includes privacy protections and configurable
    extraction policies.
    """

    def __init__(
        self,
        overlord,
        extraction_model=None,
        confidence_threshold=0.7,
        auto_extract=True,
        extraction_interval=1,  # Process every n messages
        max_history_tokens=1000,
        opt_out_users: Set[int] = None,
        whitelist_users: Set[int] = None,
        blacklist_users: Set[int] = None,
        retention_days: int = 365,  # Default to 1 year retention
        similarity_threshold: float = 0.3,  # Threshold for semantic deduplication
    ):
        """
        Initialize the MemoryExtractor.

        Args:
            overlord: The MUXI overlord that manages memory
            extraction_model: Model for extraction (may differ from agent model)
            confidence_threshold: Minimum confidence level (0.0-1.0) to store info
            auto_extract: Whether to automatically extract after conversations
            extraction_interval: Process every n messages (1=every message)
            max_history_tokens: Maximum token count for conversation history
            opt_out_users: Set of user IDs that have opted out of extraction
            whitelist_users: If set, only these users will have extraction
            blacklist_users: These users will be excluded from extraction
            retention_days: Number of days to retain extracted information
            similarity_threshold: Distance threshold for semantic deduplication (0.0-1.0)
                Lower values mean stricter matching. Default 0.3 means >77% similarity.
        """
        self.overlord = overlord
        self.extraction_model = extraction_model
        self.confidence_threshold = confidence_threshold
        self.auto_extract = auto_extract
        self.extraction_interval = extraction_interval
        self.max_history_tokens = max_history_tokens
        self.opt_out_users = opt_out_users or set()
        self.whitelist_users = whitelist_users
        self.blacklist_users = blacklist_users or set()
        self.retention_days = retention_days
        self.similarity_threshold = similarity_threshold

        # Add default privacy settings
        self._sensitive_key_patterns = {
            "password",
            "social_security",
            "ssn",
            "credit_card",
            "bank_account",
            "passport",
            "license",
            "secret",
            "private",
            "confidential",
        }

    async def process_conversation_turn(
        self, user_message, agent_response, user_id, message_count=1
    ):
        """
        Process a conversation turn and extract information if needed.

        This method analyzes a single user-agent interaction to extract
        relevant user information, applying all configured filters and
        extraction policies.

        Args:
            user_message: The message from the user
            agent_response: The response from the agent
            user_id: The user's ID
            message_count: Current message count for this user
        """
        if not self.auto_extract:
            return

        # Skip extraction for anonymous users in multi-user mode only
        # In single-user mode, user_id="0" is normal and expected
        if self.overlord.is_multi_user and (user_id == 0 or user_id == "0"):
            return

        # Skip extraction for users who have opted out
        if user_id in self.opt_out_users:
            return

        # Skip extraction for blacklisted users
        if self.blacklist_users and user_id in self.blacklist_users:
            return

        # Skip extraction for users not in whitelist (if whitelist is enabled)
        if self.whitelist_users is not None and user_id not in self.whitelist_users:
            return

        # Only process every n messages based on extraction_interval
        if message_count % self.extraction_interval != 0:
            return

        # Create conversation context from this turn
        # Handle case where agent hasn't responded yet (agent_response is empty)
        if agent_response and agent_response.strip():
            conversation = f"User: {user_message}\nAssistant: {agent_response}"
        else:
            # No agent response yet - just use the user message
            # This happens when extraction is called before the agent responds
            conversation = (
                f"User: {user_message}\n(Note: Extract from user's statement alone, agent hasn't responded yet)"
            )

        # Extract information
        extraction_results = await self._extract_user_information(conversation)

        # Process and store results if confidence threshold is met
        await self._process_extraction_results(extraction_results, user_id)

    def opt_out_user(self, user_id: int) -> bool:
        """
        Add a user to the opt-out list, preventing future extraction.

        This method allows users to opt out of automatic information
        extraction for privacy reasons.

        Args:
            user_id: The user ID to opt out

        Returns:
            True if successful, False if already opted out
        """
        if user_id in self.opt_out_users:
            return False

        self.opt_out_users.add(user_id)
        return True

    def opt_in_user(self, user_id: int) -> bool:
        """
        Remove a user from the opt-out list, enabling future extraction.

        This method allows users who previously opted out to opt back in
        to automatic information extraction.

        Args:
            user_id: The user ID to opt in

        Returns:
            True if successful, False if already opted in
        """
        if user_id not in self.opt_out_users:
            return False

        self.opt_out_users.remove(user_id)
        return True

    async def purge_user_data(self, user_id: int) -> bool:
        """
        Purge all automatically extracted data for a user.

        This method removes all information that was automatically extracted
        for a user. This supports privacy requirements like data deletion requests.

        Note: This is a legacy method. The old context_memory system has been
        replaced by rich collections (user_identity, relationships, work_projects).
        This method is preserved for API compatibility but currently does nothing.

        Args:
            user_id: The user ID to purge data for

        Returns:
            True (always successful - no-op)
        """
        # Skip for anonymous users
        if user_id == 0:
            return True

        # Legacy method - old context_memory system has been removed.
        # Automatic extraction now uses rich collections which have their own
        # purge mechanisms via the long_term_memory interface.
        observability.observe(
            event_type=observability.SystemEvents.SYSTEM_ACTION,
            level=observability.EventLevel.WARNING,
            description="purge_user_data called on legacy MemoryExtractor",
            data={
                "user_id": user_id,
                "note": "This method is deprecated - use rich collections directly",
            },
        )

        return True

    async def _extract_user_information(self, conversation):
        """
        Extract user information using the specified LLM.

        This method sends the conversation to an LLM with a specialized
        prompt to extract structured information about the user.

        Args:
            conversation: The conversation text to analyze

        Returns:
            A dictionary of extracted information with confidence scores
        """
        # Use the specified extraction model if available, otherwise use overlord's default
        model = self.extraction_model or self.overlord.default_model

        # Create extraction prompt
        prompt = self._create_extraction_prompt(conversation)

        # Generate extraction results
        try:
            extraction_response = await model.generate_text(prompt)
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.EXTENSION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "model": model._model if hasattr(model, "_model") else "unknown",
                    "component": "memory_extractor",
                    "operation": "generate_extraction",
                },
                description="Memory extractor failed to generate extraction response from model",
            )
            return {"extracted_info": []}

        # Parse results into structured format
        try:
            # Remove markdown code blocks if present
            clean_response = extraction_response.strip()
            if clean_response.startswith("```"):
                # Find the end of the first line (json marker)
                first_newline = clean_response.find("\n")
                if first_newline > 0:
                    clean_response = clean_response[first_newline + 1:]
                # Remove the closing ```
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3].strip()

            # Parse JSON response (primary approach)
            extraction_results = json.loads(clean_response)
        except json.JSONDecodeError:
            # Fallback parsing if LLM doesn't return valid JSON
            extraction_results = self._parse_fallback_extraction(extraction_response)

        return extraction_results

    def _create_extraction_prompt(self, conversation):
        """
        Create an optimized prompt for information extraction.

        This method builds a carefully designed prompt that instructs
        the LLM how to extract information while respecting privacy
        and providing structured output with confidence scores.

        Args:
            conversation: The conversation text to analyze

        Returns:
            A prompt string for the LLM
        """
        privacy_guidelines = (
            "IMPORTANT PRIVACY GUIDELINES:\n"
            "- DO NOT extract sensitive information like passwords, credit cards, SSNs, etc.\n"
            "- DO NOT extract personal contact information unless clearly relevant\n"
            "- Focus on preferences, interests, and non-sensitive personal details\n"
            "- Prefer general categories over specific identifiers\n\n"
        )

        # Get current year for age conversion
        import datetime

        current_year = datetime.datetime.now().year

        age_conversion_guidelines = (
            "AGE CONVERSION RULE:\n"
            f"- Current year is {current_year}\n"
            "- When extracting age information, ALWAYS convert it to year of birth\n"
            "- For example: if someone says they are 25 years old, write:\n"
            f'  "memory": "Was born in {current_year - 25}"\n'
            "- NOT: 'Is 25 years old' or 'year_of_birth: 2000'\n"
            "- This ensures the information stays accurate over time\n\n"
        )

        extraction_rules = (
            "EXTRACTION RULES:\n"
            "ONLY extract information when the user explicitly SHARES or STATES facts about themselves.\n\n"
            "DO extract when the user says:\n"
            "- Personal information: 'My name is...', 'I work at...', 'I live in...', 'I am X years old'\n"
            "- Preferences: 'I prefer X over Y', 'I like/love/enjoy X', 'I hate/dislike X', 'My favorite X is Y'\n"
            "- Habits/routines: 'I usually...', 'I always...', 'Every day/week I...'\n"
            "- Family/relationships: 'My sister...', 'I have a friend who...', 'My colleague...'\n"
            "- Goals/plans: 'I want to...', 'I'm planning to...', 'My goal is...'\n"
            "- Past experiences: 'I worked at...', 'I studied...', 'I visited...'\n\n"
            "DO NOT extract when the user is:\n"
            "- Asking questions: 'What is X?', 'How does Y work?', 'Can you explain Z?'\n"
            "- Requesting information: 'Tell me about...', 'Show me...', 'Give me examples of...'\n"
            "- Making general statements about topics (not about themselves)\n"
            "- Discussing hypotheticals: 'What if...', 'Suppose...', 'Imagine...'\n\n"
            "If the user asks a question, DO NOT infer preferences from their question.\n"
            "Asking 'What is FastAPI?' does NOT mean they prefer or use FastAPI.\n\n"
        )

        collection_guidelines = (
            "COLLECTION SELECTION:\n"
            "For each extracted fact, assign it to the most appropriate collection:\n"
            "- conversations: Raw chat history and full message exchanges\n"
            "- user_identity: Personal information like name, age, location, occupation, contact details\n"
            "- preferences: Likes, dislikes, favorites, preferences, opinions\n"
            "- relationships: Family, friends, colleagues, social connections\n"
            "- activities: Hobbies, interests, routines, habits, regular activities\n"
            "- goals: Aspirations, plans, objectives, desires, future intentions\n"
            "- history: Past experiences, stories, achievements, background\n"
            "- context: General knowledge, facts, observations, miscellaneous info\n\n"
        )

        return (
            "Based on the following conversation, extract important information about the user "
            "that should be remembered for future interactions. For each piece of information, "
            "include:\n"
            "1. The specific information (value)\n"
            "2. The fact type (e.g., name, location, preference)\n"
            "3. A confidence score (0.0-1.0) indicating how certain you are\n"
            "4. An importance score (0.0-1.0) indicating how important this is to remember\n"
            "5. The collection it should be stored in (see collection guidelines below)\n\n"
            "Format your response as a JSON object with the following structure:\n"
            "{\n"
            '  "extracted_info": [\n'
            "    {\n"
            '      "memory": "The user\'s name is John Doe",\n'
            '      "confidence": 0.95,\n'
            '      "importance": 0.9,\n'
            '      "collection": "user_identity"\n'
            "    },\n"
            "    ...\n"
            "  ]\n"
            "}\n\n"
            "IMPORTANT: Write memories as natural, complete sentences like:\n"
            "- 'The user works at TechCorp as a software engineer'\n"
            "- 'Enjoys hiking on weekends'\n"
            "- 'Has a sister who lives in Boston'\n"
            "- 'Was born in 1995' (not 'year_of_birth: 1995')\n\n"
            + extraction_rules
            + privacy_guidelines
            + age_conversion_guidelines
            + collection_guidelines
            + f"Conversation:\n{conversation}\n\n"
            "If there is no relevant information to extract, return an empty array for "
            "extracted_info.\n\n"
            "IMPORTANT: Always follow the extraction rules and age conversion rule above."
        )

    async def _process_extraction_results(self, extraction_results, user_id):
        """
        Process extraction results and update context memory.

        This method analyzes the extraction results, applies confidence
        thresholds, checks for sensitive information, handles conflicts
        with existing knowledge, and stores the validated information.

        Args:
            extraction_results: Dictionary of extracted information
            user_id: The user's ID
        """
        if not extraction_results or "extracted_info" not in extraction_results:
            return

        # Process each extracted item
        memories_to_store = []
        for item in extraction_results["extracted_info"]:
            # Skip items below confidence threshold
            if item["confidence"] < self.confidence_threshold:
                continue

            # Get the memory sentence
            memory = item.get("memory")
            if not memory:
                # Backwards compatibility: try to construct from fact_type and value
                fact_type = item.get("fact_type", item.get("key"))
                value = item.get("value")
                if fact_type and value:
                    memory = f"{fact_type}: {value}"
                else:
                    continue

            importance = item["importance"]
            collection = item.get("collection", "context")

            # Skip extraction of sensitive information
            if self._is_sensitive_information_sentence(memory):
                continue

            # Add to memories to store
            memories_to_store.append(
                {
                    "memory": memory,
                    "importance": importance,
                    "confidence": item["confidence"],
                    "collection": collection,
                    "timestamp": time.time(),
                }
            )

        # Store memories in long-term memory if any exist
        if (
            memories_to_store
            and hasattr(self.overlord, "long_term_memory")
            and self.overlord.long_term_memory
        ):
            # Handle multi-user mode
            external_user_id = user_id if self.overlord.is_multi_user else None

            for memory_data in memories_to_store:
                memory_content = memory_data["memory"]
                collection = memory_data["collection"]

                # Create metadata
                memory_metadata = {
                    "confidence": memory_data["confidence"],
                    "importance": memory_data["importance"],
                    "extracted_at": memory_data["timestamp"],
                    "source": "extraction",
                    "user_id": str(user_id),
                    "agent_id": getattr(self.overlord, "current_agent", None) or "overlord",
                    "collection": collection,  # Keep in metadata for reference
                }

                try:
                    # Check for semantically similar memories before storing
                    should_store = True

                    # Use long_term_memory's search if available for de-duplication
                    if hasattr(self.overlord.long_term_memory, "search"):
                        # Search for similar existing memories
                        # Build search params based on backend type
                        search_params = {
                            "query": memory_content,
                            "limit": 1,
                        }
                        if self.overlord.is_multi_user:
                            search_params["external_user_id"] = external_user_id
                            search_params["collection"] = collection
                        else:
                            search_params["user_id"] = user_id
                            # SQLiteMemory doesn't support collection parameter

                        existing = await self.overlord.long_term_memory.search(**search_params)

                        if existing:
                            # Check the first result for similarity
                            # Score = 1/(1+distance), so higher score = more similar
                            # Score=1.0 means identical, score>0.9 means very similar (distance<0.11)
                            first_result = existing[0] if isinstance(existing, list) else existing
                            score = first_result.get("score", 0.0) if isinstance(first_result, dict) else 0.0

                            # Convert distance threshold to score threshold
                            # If similarity_threshold=0.3, we skip when distance<0.3
                            # Which means score > 1/(1+0.3) = 0.769
                            score_threshold = 1.0 / (1.0 + self.similarity_threshold)

                            if score > score_threshold:
                                # Memory is very similar to existing one - skip to avoid duplicate
                                observability.observe(
                                    event_type=observability.SystemEvents.OPERATION_COMPLETED,
                                    level=observability.EventLevel.DEBUG,
                                    data={
                                        "new_content": memory_content[:100],
                                        "existing_content": first_result.get("text", "")[:100],
                                        "similarity_score": score,
                                        "threshold": score_threshold,
                                    },
                                    description=(
                                        f"Skipping duplicate memory (similarity: {score:.3f} > {score_threshold:.3f})",
                                    ),
                                )
                                should_store = False
                            else:
                                # Log when we allow a similar memory through
                                observability.observe(
                                    event_type=observability.SystemEvents.OPERATION_COMPLETED,
                                    level=observability.EventLevel.DEBUG,
                                    data={
                                        "new_content": memory_content[:100],
                                        "existing_content": first_result.get("text", "")[:100],
                                        "similarity_score": score,
                                        "threshold": score_threshold,
                                    },
                                    description=(
                                        f"Storing similar memory (similarity: {score:.3f} <= {score_threshold:.3f})",
                                    ),
                                )

                    if should_store:
                        # Build add params - use user_id for both backends
                        add_params = {
                            "content": memory_content,
                            "metadata": memory_metadata,
                            "user_id": user_id,
                            "collection": collection,
                        }

                        await self.overlord.long_term_memory.add(**add_params)

                        # Invalidate identity synopsis cache if this affects identity collections
                        if collection in ["user_identity", "relationships", "work_projects"]:
                            try:
                                if hasattr(self.overlord, 'user_context_manager'):
                                    await self.overlord.user_context_manager.invalidate_identity_synopsis_cache(
                                        user_id
                                    )
                            except Exception:
                                pass  # Cache invalidation failure is non-critical
                except Exception as e:
                    # Log memory storage failure for debugging while continuing execution
                    observability.observe(
                        event_type=observability.SystemEvents.EXTENSION_FAILED,
                        level=observability.EventLevel.ERROR,
                        description=f"Failed to store extracted memory in long-term memory: {str(e)}",
                        data={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "memory_content": (
                                memory_content[:100] + "..."
                                if len(memory_content) > 100
                                else memory_content
                            ),
                            "collection": collection,
                            "user_id": str(user_id),
                            "component": "memory_extractor",
                            "operation": "long_term_memory_add",
                        },
                    )

    def _is_sensitive_information(self, key: str, value: Any) -> bool:
        """
        Check if the information appears to be sensitive.

        This method applies privacy rules to detect potentially sensitive
        information that shouldn't be automatically stored, including
        PII, financial data, and security information.

        Args:
            key: The category key
            value: The value to check

        Returns:
            True if sensitive, False otherwise
        """
        key_lower = key.lower()

        # Check for sensitive key patterns
        for pattern in self._sensitive_key_patterns:
            if pattern in key_lower:
                return True

        # Check for common sensitive value patterns
        if isinstance(value, str):
            # Credit card pattern (sequence of digits)
            if len(value.replace(" ", "").replace("-", "")) >= 15:
                digits_only = "".join(c for c in value if c.isdigit())
                if len(digits_only) >= 15:
                    return True

            # Check for email addresses if not in allowed keys
            if "@" in value and "." in value and key_lower not in {"email", "contact"}:
                return True

            # Phone number pattern if not in allowed keys
            if len("".join(c for c in value if c.isdigit())) >= 10:
                if key_lower not in {"phone", "contact", "mobile"}:
                    return True

        return False

    def _should_update_existing(self, key, new_value, existing_value, importance):
        """
        Determine if existing information should be updated.

        This method implements the conflict resolution strategy when
        newly extracted information conflicts with existing knowledge.

        Args:
            key: The key/category of the information
            new_value: The newly extracted value
            existing_value: The existing value in context memory
            importance: The importance score of the new value

        Returns:
            True if the existing information should be updated, False otherwise
        """
        # For complex updates like adding to lists, merging objects, etc.
        # Will need to implement category-specific logic

        # Simple version - higher importance items replace existing items
        if isinstance(existing_value, dict) and "importance" in existing_value:
            return importance > existing_value["importance"]

        # Default to updating
        return True

    def _is_sensitive_information_sentence(self, sentence: str) -> bool:
        """
        Check if the sentence contains sensitive information.

        Args:
            sentence: The memory sentence to check

        Returns:
            True if sensitive, False otherwise
        """
        sentence_lower = sentence.lower()

        # Check for sensitive patterns in the sentence
        for pattern in self._sensitive_key_patterns:
            if pattern in sentence_lower:
                return True

        # Check for credit card patterns
        if any(len("".join(c for c in word if c.isdigit())) >= 15 for word in sentence.split()):
            return True

        # Check for SSN patterns (XXX-XX-XXXX)
        import re

        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", sentence):
            return True

        return False

    def _parse_fallback_extraction(self, text):
        """
        Parse extraction results from text if JSON parsing fails.

        This method provides a fallback mechanism when the LLM response
        isn't valid JSON, attempting to extract structured information
        from free-text format.

        Args:
            text: The raw text response from the LLM

        Returns:
            A dictionary with extracted_info field
        """
        # Implement fallback parsing logic for when the LLM doesn't return valid JSON
        lines = text.strip().split("\n")
        extracted_info = []

        current_item = {}
        for line in lines:
            line = line.strip()
            if not line:
                if (
                    current_item
                    and ("fact_type" in current_item or "key" in current_item)
                    and "value" in current_item
                ):
                    # Normalize 'key' to 'fact_type' for consistency
                    if "key" in current_item and "fact_type" not in current_item:
                        current_item["fact_type"] = current_item["key"]
                        del current_item["key"]
                    # Add default values if missing
                    if "confidence" not in current_item:
                        current_item["confidence"] = 0.7
                    if "importance" not in current_item:
                        current_item["importance"] = 0.5
                    if "collection" not in current_item:
                        current_item["collection"] = "context"
                    extracted_info.append(current_item)
                current_item = {}
            elif ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                if key in ["key", "category", "fact_type"]:
                    current_item["fact_type"] = value
                elif key in ["value", "information"]:
                    current_item["value"] = value
                elif key == "confidence":
                    try:
                        current_item["confidence"] = float(value)
                    except ValueError:
                        current_item["confidence"] = 0.7
                elif key == "importance":
                    try:
                        current_item["importance"] = float(value)
                    except ValueError:
                        current_item["importance"] = 0.5
                elif key == "collection":
                    current_item["collection"] = value

        # Add the last item if it exists
        if (
            current_item
            and ("fact_type" in current_item or "key" in current_item)
            and "value" in current_item
        ):
            # Normalize 'key' to 'fact_type' for consistency
            if "key" in current_item and "fact_type" not in current_item:
                current_item["fact_type"] = current_item["key"]
                del current_item["key"]
            # Add default values if missing
            if "confidence" not in current_item:
                current_item["confidence"] = 0.7
            if "importance" not in current_item:
                current_item["importance"] = 0.5
            if "collection" not in current_item:
                current_item["collection"] = "context"
            extracted_info.append(current_item)

        return {"extracted_info": extracted_info}
