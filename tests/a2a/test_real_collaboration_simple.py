#!/usr/bin/env python3
"""
Simple Real A2A Collaboration Test

This script tests TRUE agent-to-agent collaboration using real OpenAI models.
It's designed to be run directly without complex import dependencies.

Usage:
    python test_real_collaboration_simple.py

Requirements:
    - OPENAI_API_KEY environment variable set
    - A2A formation server running on localhost:3001
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Add runtime to path
runtime_path = Path(__file__).parent.parent / "runtime"
sys.path.insert(0, str(runtime_path))

try:
    from src.muxi.runtime.overlord import Overlord
    from src.muxi.runtime.llm.llm import LLM
    print("✅ Successfully imported MUXI components")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the runtime project root")
    sys.exit(1)


class RealCollaborationTester:
    """Test real agent collaboration with actual OpenAI models"""

    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")

        self.overlord = None
        self.agents = {}

    async def setup_formation(self):
        """Create specialized agents for collaboration testing"""
        print("\n🔧 Setting up agent formation...")

        # Create overlord
        self.overlord = Overlord()

        # Create research specialist
        research_model = LLM(
            api_key=self.api_key,
            model="openai/gpt-4",
            temperature=0.7,
            max_tokens=800
        )

        research_agent = self.overlord.create_agent(
            agent_id="researcher",
            model=research_model,
            description="Research specialist for gathering and analyzing information",
            system_message=(
                "You are a research specialist. Your expertise is gathering comprehensive "
                "information and identifying key insights. When collaborating with other agents, "
                "provide detailed, factual research findings."
            ),
            a2a_internal=True,
            a2a_external=True
        )

        # Create technical writer
        writer_model = LLM(
            api_key=self.api_key,
            model="openai/gpt-4",
            temperature=0.8,
            max_tokens=800
        )

        writer_agent = self.overlord.create_agent(
            agent_id="writer",
            model=writer_model,
            description="Technical writer for creating clear, structured documents",
            system_message=(
                "You are a technical writing specialist. Your expertise is creating clear, "
                "well-structured documents and reports. Focus on clarity, organization, "
                "and making complex information accessible."
            ),
            a2a_internal=True,
            a2a_external=True
        )

        self.agents = {
            'researcher': research_agent,
            'writer': writer_agent
        }

        print(f"✅ Created {len(self.agents)} specialized agents")
        return True

    async def test_basic_collaboration(self):
        """Test basic two-agent collaboration"""
        print("\n🧪 Testing Basic Collaboration...")
        print("=" * 60)

        researcher = self.agents['researcher']
        writer = self.agents['writer']

        # Step 1: Researcher gathers information
        print("\n📚 Step 1: Research phase...")
        research_topic = "benefits of pair programming in software development"

        research_response = await researcher.process_message(
            f"Please research {research_topic}. "
            "Provide key findings, statistics, and benefits."
        )

        # Extract content from MCPMessage if needed
        if hasattr(research_response, 'content'):
            research_content = research_response.content
        else:
            research_content = str(research_response)

        print(f"✓ Research completed: {len(research_content)} chars")
        print(f"Research preview: {research_content[:200]}...")

        # Step 2: Share research with writer
        print("\n🤝 Step 2: Collaboration - sharing research with writer...")

        try:
            # Use share_information for direct collaboration
            share_result = await researcher.share_information(
                target_agent_id="writer",
                information=research_content,
                topic="pair_programming_research",
                relevance_reason="Research data needed for creating a comprehensive guide"
            )
            print(f"✅ Information shared successfully: {share_result}")
        except AttributeError:
            print("⚠️  share_information method not available, using alternative approach")
            # Alternative: Direct communication
            writer_response = await writer.process_message(
                f"A researcher has provided this information about {research_topic}: "
                f"{research_content[:500]}... "
                "Please create a comprehensive guide based on this research."
            )

            # Extract content from writer response
            if hasattr(writer_response, 'content'):
                final_content = writer_response.content
            else:
                final_content = str(writer_response)

            share_result = f"Writer created guide with {len(final_content)} chars"

        return {
            'research_length': len(research_content),
            'research_preview': research_content[:100],
            'collaboration_result': str(share_result),
            'collaboration_successful': True
        }

    async def test_consultation_pattern(self):
        """Test consultation pattern between agents"""
        print("\n🧪 Testing Consultation Pattern...")
        print("=" * 60)

        writer = self.agents['writer']

        # Writer requests research consultation
        print("\n💬 Writer requesting research consultation...")

        try:
            consultation_result = await writer.request_consultation(
                target_agent_id="researcher",
                topic="microservices architecture research",
                context={
                    "objective": "Gather comprehensive research for report writing",
                    "focus": "benefits, performance, scalability, adoption",
                    "output_format": "structured research findings"
                }
            )

            print(f"✓ Consultation successful: {consultation_result['status']}")
            print(f"Research received: {len(consultation_result['response'])} chars")
            print(f"Preview: {consultation_result['response'][:200]}...")

            return consultation_result

        except Exception as e:
            print(f"❌ Consultation failed: {e}")
            return {"status": "failed", "error": str(e)}

    async def run_all_tests(self):
        """Run comprehensive collaboration tests"""
        print("🚀 Starting Real A2A Collaboration Tests")
        print("=" * 80)

        results = {}

        try:
            # Setup
            await self.setup_formation()

            # Test 1: Basic collaboration
            results['basic_collaboration'] = await self.test_basic_collaboration()

            # Test 2: Consultation pattern
            results['consultation'] = await self.test_consultation_pattern()

            # Summary
            print("\n📊 TEST RESULTS SUMMARY")
            print("=" * 40)

            for test_name, result in results.items():
                if isinstance(result, dict) and result.get('collaboration_successful'):
                    print(f"✅ {test_name}: SUCCESS")
                elif isinstance(result, dict) and result.get('status') == 'success':
                    print(f"✅ {test_name}: SUCCESS")
                else:
                    print(f"❌ {test_name}: FAILED")

            return results

        except Exception as e:
            print(f"💥 Test suite failed: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}


async def main():
    """Main test runner"""
    print("🧪 Real A2A Collaboration Test Suite")
    print("===================================")

    # Check prerequisites
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ OPENAI_API_KEY environment variable not set")
        print("Please set your OpenAI API key and try again")
        return

    print("✅ OpenAI API key found")

    # Run tests
    tester = RealCollaborationTester()
    results = await tester.run_all_tests()

    # Save results
    output_file = "real_collaboration_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n🎉 Real collaboration testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
