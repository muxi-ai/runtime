#!/usr/bin/env python3
"""
Test script for multilingual intent detection

This script demonstrates the IntentDetectionService's ability to
detect intents in multiple languages without hardcoded keywords.
"""

import asyncio
from src.muxi.services.intent import IntentDetectionService
from src.muxi.services.llm import LLM
from src.muxi.datatypes.intent import IntentType, IntentDetectionContext


async def test_multilingual_intent():
    """Test intent detection in multiple languages."""

    # Initialize the service
    llm_service = LLM(model="openai/gpt-4", api_key=None)  # Will use environment variable

    intent_detector = IntentDetectionService(llm_service=llm_service, enable_cache=True)

    # Test cases in different languages
    test_cases = [
        # Query type detection
        {
            "text": "Do you remember what we discussed yesterday?",
            "intent_type": IntentType.QUERY_TYPE,
            "expected": "memory",
            "language": "English",
        },
        {
            "text": "¿Recuerdas lo que hablamos ayer?",
            "intent_type": IntentType.QUERY_TYPE,
            "expected": "memory",
            "language": "Spanish",
        },
        {
            "text": "你还记得我们昨天讨论的内容吗？",
            "intent_type": IntentType.QUERY_TYPE,
            "expected": "memory",
            "language": "Chinese",
        },
        {
            "text": "What is machine learning?",
            "intent_type": IntentType.QUERY_TYPE,
            "expected": "knowledge",
            "language": "English",
        },
        {
            "text": "Qu'est-ce que l'apprentissage automatique?",
            "intent_type": IntentType.QUERY_TYPE,
            "expected": "knowledge",
            "language": "French",
        },
        # Schedule type detection
        {
            "text": "Remind me every Monday at 9am",
            "intent_type": IntentType.SCHEDULE_TYPE,
            "expected": "recurring",
            "language": "English",
        },
        {
            "text": "Rappelle-moi demain à 14h",
            "intent_type": IntentType.SCHEDULE_TYPE,
            "expected": "one_time",
            "language": "French",
        },
        {
            "text": "毎週月曜日の午前9時に思い出させてください",
            "intent_type": IntentType.SCHEDULE_TYPE,
            "expected": "recurring",
            "language": "Japanese",
        },
        # Clarification category detection
        {
            "text": "I need to know your budget for this project",
            "intent_type": IntentType.CLARIFICATION_CATEGORY,
            "expected": "budget",
            "language": "English",
        },
        {
            "text": "¿Cuál es tu presupuesto para este proyecto?",
            "intent_type": IntentType.CLARIFICATION_CATEGORY,
            "expected": "budget",
            "language": "Spanish",
        },
        {
            "text": "Wann brauchen Sie das fertig?",
            "intent_type": IntentType.SCHEDULE_TYPE,
            "expected": "one_time",
            "language": "German",
        },
        # Error type detection
        {
            "text": "Error: Out of memory while processing large file",
            "intent_type": IntentType.ERROR_TYPE,
            "expected": "memory",
            "language": "English",
        },
        {
            "text": "Erreur: Délai d'attente dépassé lors de la connexion",
            "intent_type": IntentType.ERROR_TYPE,
            "expected": "timeout",
            "language": "French",
        },
    ]

    # Run tests
    print("Testing Multilingual Intent Detection")
    print("=" * 50)

    for test in test_cases:
        print(f"\nLanguage: {test['language']}")
        print(f"Text: {test['text']}")
        print(f"Intent Type: {test['intent_type'].value}")

        try:
            result = await intent_detector.detect_intent(
                text=test["text"], intent_type=test["intent_type"], context=IntentDetectionContext()
            )

            print(f"Detected Intent: {result.intent}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Expected: {test['expected']}")
            print(f"Match: {'✓' if result.intent == test['expected'] else '✗'}")

            if result.reasoning:
                print(f"Reasoning: {result.reasoning}")

        except Exception as e:
            print(f"Error: {str(e)}")

    # Show cache statistics
    print("\n" + "=" * 50)
    print("Cache Statistics:")
    if intent_detector.cache:
        stats = intent_detector.cache.get_stats()
        print(f"Cache Size: {stats['size']}")
        print(f"Hit Rate: {stats['hit_rate']:.2%}")
        print(f"Hits: {stats['hits']}")
        print(f"Misses: {stats['misses']}")


if __name__ == "__main__":
    asyncio.run(test_multilingual_intent())
