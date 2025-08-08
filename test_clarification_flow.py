"""Test clarification flow."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        print("\n=== First message (ambiguous) ===")
        response1 = await overlord.chat(
            message="I need help with a scraper",
            user_id="test_user",
            session_id="test_session",
            stream=False
        )
        
        print(f"Response: {response1.content}")
        print(f"Is clarification: {response1.metadata and response1.metadata.get('clarification')}")
        
        print("\n=== Second message (providing details) ===")
        response2 = await overlord.chat(
            message="A Python web scraper for extracting product prices",
            user_id="test_user",
            session_id="test_session",
            stream=False
        )
        
        print(f"Response preview: {response2.content[:200]}...")
        print(f"Is clarification: {response2.metadata and response2.metadata.get('clarification')}")
        
        # Check if it contains relevant keywords
        response_lower = response2.content.lower()
        keywords = ["python", "scraper", "price", "extract", "beautifulsoup", "requests", "selenium"]
        found_keywords = [k for k in keywords if k in response_lower]
        print(f"Found keywords: {found_keywords}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())