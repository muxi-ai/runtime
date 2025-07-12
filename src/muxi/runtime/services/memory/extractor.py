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

        # Skip extraction for anonymous users (user_id=0)
        if user_id == 0:
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
        conversation = f"User: {user_message}\nAssistant: {agent_response}"

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
        for a user, while preserving manually added information. This supports
        privacy requirements like data deletion requests.

        Args:
            user_id: The user ID to purge data for

        Returns:
            True if successful, False otherwise
        """
        # Skip for anonymous users
        if user_id == 0:
            return True

        # Get existing context to find auto-extracted entries
        context = await self.overlord.get_user_context(user_id=user_id)

        # Look for keys that were created by automatic extraction
        to_delete = []

        for key, value in context.items():
            if isinstance(value, dict) and value.get("source") == "automatic_extraction":
                to_delete.append(key)

        # Clear these specific keys
        if to_delete:
            return await self.overlord.clear_user_context(user_id=user_id, keys=to_delete)

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
        print("[DEBUG Extractor] Sending extraction prompt to model...")
        try:
            extraction_response = await model.generate_text(prompt)
            print(f"[DEBUG Extractor] Got extraction response: {extraction_response[:200]}...")
        except Exception as e:
            print(f"[DEBUG Extractor] ERROR generating response: {e}")
            import traceback

            traceback.print_exc()
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
            print(f"[DEBUG Extractor] Parsed extraction results: {extraction_results}")
        except json.JSONDecodeError:
            print("[DEBUG Extractor] JSON decode failed, using fallback parsing")
            print(f"[DEBUG Extractor] Full response: {extraction_response}")
            # Fallback parsing if LLM doesn't return valid JSON
            extraction_results = self._parse_fallback_extraction(extraction_response)
            print(f"[DEBUG Extractor] Fallback parsing result: {extraction_results}")

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
            + privacy_guidelines
            + age_conversion_guidelines
            + collection_guidelines
            + f"Conversation:\n{conversation}\n\n"
            "If there is no relevant information to extract, return an empty array for "
            "extracted_info.\n\n"
            "IMPORTANT: Always follow the age conversion rule above when dealing with age information."
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
        print(f"[DEBUG Extractor] Processing extraction results for user {user_id}")
        if not extraction_results or "extracted_info" not in extraction_results:
            print("[DEBUG Extractor] No extraction results or missing 'extracted_info' key")
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
            print(
                f"[DEBUG Extractor] Storing {len(memories_to_store)} memories in long-term memory"
            )

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

                print(
                    f"[DEBUG Extractor] Storing memory: '{memory_content}' (collection: {collection})"
                )
                try:
                    result = await self.overlord.long_term_memory.add(
                        content=memory_content,
                        metadata=memory_metadata,
                        external_user_id=external_user_id,
                        collection=collection,
                    )
                    print(f"[DEBUG Extractor] Stored memory with ID: {result}")
                except Exception as e:
                    print(f"[DEBUG Extractor] ERROR storing memory: {e}")
                    import traceback

                    traceback.print_exc()

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
