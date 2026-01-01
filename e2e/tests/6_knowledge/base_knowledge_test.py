#!/usr/bin/env python3
"""Base test class for Area 6 Knowledge tests with standardized patterns."""

import sys
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import json

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402

# Import from common module
from common import BaseE2ETest  # noqa: E402
from common import TestOutputFormatter  # noqa: E402


class BaseKnowledgeTest(BaseE2ETest):
    """Base class for Knowledge tests."""

    # Shared formation directory for all knowledge tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-knowledge"

    # Knowledge domain configurations
    KNOWLEDGE_DOMAINS = {
        "automaze": {
            "agent_name": "automaze",
            "knowledge_types": ["faq", "documentation", "services"],
            "expected_keywords": ["automaze", "service", "solution", "automation", "testing"],
        },
        "muxi": {
            "agent_name": "muxi",
            "knowledge_types": ["pricing", "business_plan", "features"],
            "expected_keywords": ["muxi", "price", "plan", "tier", "runtime"],
        },
    }

    # Query categories for testing different knowledge retrieval patterns
    QUERY_CATEGORIES = {
        "services": {
            "questions": [
                "What services does {domain} offer?",
                "Tell me about {domain}'s solutions",
                "What can {domain} help with?",
            ],
            "expected_content_length": 100,
        },
        "pricing": {
            "questions": [
                "What are {domain}'s pricing plans?",
                "How much does {domain} cost?",
                "Tell me about {domain}'s pricing model",
            ],
            "expected_content_length": 80,
        },
        "features": {
            "questions": [
                "What features does {domain} provide?",
                "What are {domain}'s capabilities?",
                "What can I do with {domain}?",
            ],
            "expected_content_length": 75,
        },
        "company": {
            "questions": [
                "Tell me about {domain}",
                "What is {domain}?",
                "Who is behind {domain}?",
            ],
            "expected_content_length": 50,
        },
    }

    def __init__(self):
        """Initialize base knowledge test."""
        super().__init__()
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None
        self.knowledge_queries = []

    async def setup_knowledge_formation(self) -> Formation:
        """Setup formation with knowledge agents.

        Returns:
            Configured Formation instance
        """
        formation_path = self.FORMATION_DIR / "formation.afs"

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation

    async def query_knowledge(
        self,
        question: str,
        domain: Optional[str] = None,
        agent_name: Optional[str] = None,
        user_id: str = "test_user",
        session_id: str = "test_session",
    ) -> Tuple[bool, Any]:
        """Query knowledge through natural language.

        Args:
            question: Natural language question
            domain: Knowledge domain (automaze, muxi)
            agent_name: Specific agent to query
            user_id: User ID for the request
            session_id: Session ID for the request

        Returns:
            Tuple of (success, response)
        """
        try:
            # If domain provided but no agent_name, use domain's default agent
            if domain and not agent_name:
                agent_name = self.KNOWLEDGE_DOMAINS.get(domain, {}).get("agent_name")

            # Execute through overlord
            response = await self.overlord.chat(
                question,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
                # Create mock response object for compatibility
                response = type("MockResponse", (), {"content": response_text})()

            success = True
            self.knowledge_queries.append((question, response))

            return success, response

        except Exception as e:
            return False, f"Knowledge query error: {str(e)}"

    def validate_knowledge_response(
        self, response: Any, domain: str, query_category: str = "services"
    ) -> Dict[str, bool]:
        """Validate a knowledge response against expected criteria.

        Args:
            response: Response object to validate
            domain: Expected knowledge domain
            query_category: Category of query from QUERY_CATEGORIES

        Returns:
            Dictionary of validation results
        """
        validation = {
            "has_content": False,
            "sufficient_length": False,
            "contains_domain_keywords": False,
            "contains_relevant_info": False,
        }

        if not response:
            return validation

        # Extract content
        content = response.content if hasattr(response, "content") else str(response)
        content_lower = content.lower()

        # Check if response has content
        validation["has_content"] = len(content.strip()) > 0

        # Check content length based on query category
        expected_length = self.QUERY_CATEGORIES.get(query_category, {}).get(
            "expected_content_length", 50
        )
        validation["sufficient_length"] = len(content) >= expected_length

        # Check for domain-specific keywords
        if domain in self.KNOWLEDGE_DOMAINS:
            domain_keywords = self.KNOWLEDGE_DOMAINS[domain]["expected_keywords"]
            keywords_found = [kw for kw in domain_keywords if kw in content_lower]
            validation["contains_domain_keywords"] = len(keywords_found) > 0

        # Check for category-relevant information
        category_indicators = {
            "services": ["service", "offer", "solution", "provide", "help"],
            "pricing": ["price", "cost", "plan", "tier", "free", "paid", "$"],
            "features": ["feature", "capability", "function", "tool", "ability"],
            "company": ["company", "about", "founded", "team", "mission"],
        }

        if query_category in category_indicators:
            indicators = category_indicators[query_category]
            validation["contains_relevant_info"] = any(ind in content_lower for ind in indicators)

        return validation

    async def test_domain_knowledge_retrieval(
        self, domain: str, query_category: str = "services"
    ) -> Tuple[bool, str]:
        """Test knowledge retrieval for a specific domain.

        Args:
            domain: Knowledge domain to test
            query_category: Category of query to test

        Returns:
            Tuple of (success, details)
        """
        if domain not in self.KNOWLEDGE_DOMAINS:
            return False, f"Unknown domain: {domain}"

        if query_category not in self.QUERY_CATEGORIES:
            return False, f"Unknown query category: {query_category}"

        # Get a random question for this category
        questions = self.QUERY_CATEGORIES[query_category]["questions"]
        question = questions[0].format(domain=domain)

        success, response = await self.query_knowledge(question, domain=domain)

        if not success:
            return False, f"Failed to query {domain} knowledge"

        validation = self.validate_knowledge_response(response, domain, query_category)

        if all(validation.values()):
            return True, f"Successfully retrieved {domain} {query_category} knowledge"
        else:
            failed_checks = [k for k, v in validation.items() if not v]
            return False, f"Failed validation checks: {failed_checks}"

    async def test_knowledge_isolation(
        self, domain1: str, domain2: str, query_category: str = "services"
    ) -> Tuple[bool, str]:
        """Test that agents only access their own knowledge domains.

        Args:
            domain1: Primary domain
            domain2: Secondary domain (should not be accessible)
            query_category: Category of query to test

        Returns:
            Tuple of (success, details)
        """
        # Query domain2 knowledge using domain1 agent
        if domain2 not in self.KNOWLEDGE_DOMAINS:
            return False, f"Unknown domain: {domain2}"

        questions = self.QUERY_CATEGORIES[query_category]["questions"]
        question = questions[0].format(domain=domain2)

        # Force query through domain1 agent
        agent_name = self.KNOWLEDGE_DOMAINS[domain1]["agent_name"]

        success, response = await self.query_knowledge(question, agent_name=agent_name)

        if not success:
            return False, "Failed to execute cross-domain query"

        # Validate that response doesn't contain domain2 knowledge
        validation = self.validate_knowledge_response(response, domain2, query_category)

        # For isolation test, we want LACK of domain2 knowledge
        if validation["contains_domain_keywords"] or validation["contains_relevant_info"]:
            return False, f"Agent leaked {domain2} knowledge when it shouldn't have access"

        return True, f"Knowledge isolation maintained between {domain1} and {domain2}"

    async def test_multi_domain_routing(
        self, queries: List[Tuple[str, str]]
    ) -> Tuple[bool, List[str]]:
        """Test that overlord routes queries to appropriate domain agents.

        Args:
            queries: List of (question, expected_domain) tuples

        Returns:
            Tuple of (success, results)
        """
        results = []
        all_success = True

        for question, expected_domain in queries:
            success, response = await self.query_knowledge(question)  # No agent specified

            if success:
                validation = self.validate_knowledge_response(response, expected_domain)
                if validation["contains_domain_keywords"]:
                    results.append(f"✅ Routed '{question}' to {expected_domain}")
                else:
                    results.append(f"❌ Failed to route '{question}' to {expected_domain}")
                    all_success = False
            else:
                results.append(f"❌ Query failed: {question}")
                all_success = False

            # Small delay between queries
            await asyncio.sleep(1)

        return all_success, results

    async def test_knowledge_search_accuracy(
        self, domain: str, specific_queries: List[Tuple[str, List[str]]]
    ) -> Tuple[bool, List[str]]:
        """Test accuracy of knowledge search for specific topics.

        Args:
            domain: Knowledge domain to test
            specific_queries: List of (question, expected_keywords) tuples

        Returns:
            Tuple of (success, results)
        """
        results = []
        all_success = True

        for question, expected_keywords in specific_queries:
            success, response = await self.query_knowledge(question, domain=domain)

            if success:
                content = response.content if hasattr(response, "content") else str(response)
                content_lower = content.lower()

                found_keywords = [kw for kw in expected_keywords if kw.lower() in content_lower]
                keyword_ratio = len(found_keywords) / len(expected_keywords)

                if keyword_ratio >= 0.5:  # At least 50% of keywords found
                    results.append(
                        f"✅ '{question}' found {len(found_keywords)}/{len(expected_keywords)} keywords"
                    )
                else:
                    results.append(
                        f"❌ '{question}' only found {len(found_keywords)}/{len(expected_keywords)} keywords"
                    )
                    all_success = False
            else:
                results.append(f"❌ Query failed: {question}")
                all_success = False

            await asyncio.sleep(1)

        return all_success, results

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None
        self.knowledge_queries = []

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header."""
        self.formatter.print_test_header(test_name, description)

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result."""
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)

    def save_test_results(self, test_name: str, success: bool, queries: List, details: Dict = None):
        """Save test results to JSON file for analysis.

        Args:
            test_name: Name of the test
            success: Whether test passed
            queries: List of knowledge queries performed
            details: Additional test details
        """
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{test_name}.json"

        result_data = {
            "test": test_name,
            "status": "PASSED" if success else "FAILED",
            "timestamp": time.time(),
            "queries_count": len(queries),
            "queries": [
                {
                    "question": q[0],
                    "response_preview": (
                        q[1].content[:200] if hasattr(q[1], "content") else str(q[1])[:200]
                    ),
                }
                for q in queries
            ],
        }

        if details:
            result_data.update(details)

        with open(output_file, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"💾 Results saved to: {output_file}")
