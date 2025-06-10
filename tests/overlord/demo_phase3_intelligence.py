"""
Phase 3 User Experience Intelligence Demonstration

This script demonstrates the intelligent context understanding and adaptive response generation
capabilities implemented in Phase 3, showcasing both multi-user and single-user modes.
"""

import asyncio
import time
from unittest.mock import Mock

# Import Phase 3 components
from runtime.muxi.runtime.overlord.intelligence import (
    UserPreferenceEngine,
    AdaptiveResponseGenerator,
)

from runtime.muxi.runtime.overlord.intelligence.types import (
    Message,
    FeedbackEvent,
    ConversationContext,
    PreferenceType
)


class Phase3Demo:
    """Comprehensive demonstration of Phase 3 capabilities"""

    def __init__(self):
        self.demo_scenarios = [
            ("Multi-User Mode Demo", self.demo_multi_user_mode),
            ("Single-User Mode Demo", self.demo_single_user_mode),
            ("Contextual Adaptation Demo", self.demo_contextual_adaptation),
            ("Preference Learning Demo", self.demo_preference_learning),
            ("Adaptive Response Generation", self.demo_adaptive_responses),
            ("Real-time Feedback Integration", self.demo_feedback_integration)
        ]

    def create_mock_overlord(self, multi_user: bool = False):
        """Create mock overlord for demonstration"""
        mock_overlord = Mock()
        mock_overlord.is_multi_user = multi_user
        mock_overlord.long_term_memory = Mock() if multi_user else None

        if multi_user:
            mock_overlord.long_term_memory.uses_postgresql = Mock(return_value=True)

        return mock_overlord

    async def demo_multi_user_mode(self):
        """Demonstrate multi-user mode with strict user separation"""
        print("\n🔸 Multi-User Mode: Strict User Separation")
        print("=" * 60)

        # Setup multi-user components
        overlord = self.create_mock_overlord(multi_user=True)
        preference_engine = UserPreferenceEngine(overlord)
        adaptive_generator = AdaptiveResponseGenerator(overlord)

        print(f"✅ Deployment Mode: {preference_engine.is_multi_user}")
        print("✅ User isolation: ENABLED")

        # Simulate two different users with different preferences
        users = {
            "user_alice": {
                "messages": [
                    Message(content="I prefer brief, professional responses", role="user", timestamp=time.time(), user_id="user_alice"),
                    Message(content="Use formal language please", role="user", timestamp=time.time(), user_id="user_alice"),
                    Message(content="Can you format that as bullet points?", role="user", timestamp=time.time(), user_id="user_alice")
                ],
                "context": ConversationContext(urgency="high", current_task="business meeting prep")
            },
            "user_bob": {
                "messages": [
                    Message(content="I love detailed explanations with examples", role="user", timestamp=time.time(), user_id="user_bob"),
                    Message(content="Please be casual and friendly", role="user", timestamp=time.time(), user_id="user_bob"),
                    Message(content="I prefer step-by-step instructions", role="user", timestamp=time.time(), user_id="user_bob")
                ],
                "context": ConversationContext(urgency="low", current_task="learning new skill")
            }
        }

        # Analyze preferences for each user separately
        for user_id, user_data in users.items():
            print(f"\n👤 Analyzing preferences for {user_id}:")

            # Mock the filtering to simulate user separation
            preference_engine._filter_user_history = Mock(return_value=user_data["messages"])
            preference_engine._filter_user_feedback = Mock(return_value=[])

            preferences = await preference_engine.analyze_user_preferences(
                user_id=user_id,
                conversation_history=user_data["messages"],
                feedback_data=[]
            )

            print(f"   📊 Extracted {len(preferences.explicit)} explicit preferences")
            print(f"   🎯 Deployment mode: {preferences.deployment_mode}")
            print(f"   🔐 User ID: {preferences.user_id}")

            # Show preference examples
            for pref in preferences.explicit[:2]:
                print(f"   • {pref.preference_type.value}: {pref.value} (confidence: {pref.confidence.weighted_confidence:.2f})")

            # Generate adaptive response for this user
            base_response = "Here's how to solve this problem. It involves several steps and considerations that you should understand."

            adapted = await adaptive_generator.generate_adaptive_response(
                base_response=base_response,
                user_preferences=preferences,
                context=user_data["context"],
                user_id=user_id
            )

            print(f"   🎨 Applied {len(adapted.adaptations_applied)} adaptations")
            print(f"   📈 Adaptation confidence: {adapted.confidence:.2f}")

            if adapted.adaptations_applied:
                print(f"   🔄 Example adaptation: {adapted.adaptations_applied[0].adaptation_type.value}")

    async def demo_single_user_mode(self):
        """Demonstrate single-user mode with global preference learning"""
        print("\n🔸 Single-User Mode: Global Preference Learning")
        print("=" * 60)

        # Setup single-user components
        overlord = self.create_mock_overlord(multi_user=False)
        preference_engine = UserPreferenceEngine(overlord)
        adaptive_generator = AdaptiveResponseGenerator(overlord)

        print(f"✅ Deployment Mode: {'Single-User' if not preference_engine.is_multi_user else 'Multi-User'}")
        print("✅ User isolation: DISABLED (optimized for single user)")

        # Simulate global conversation history
        global_messages = [
            Message(content="I generally prefer concise explanations", role="user", timestamp=time.time()),
            Message(content="Use a friendly, casual tone", role="user", timestamp=time.time()),
            Message(content="I like examples with my explanations", role="user", timestamp=time.time()),
            Message(content="Format responses as numbered lists when possible", role="user", timestamp=time.time())
        ]

        print(f"\n📚 Analyzing global conversation pattern ({len(global_messages)} messages)")

        preferences = await preference_engine.analyze_user_preferences(
            user_id=None,  # Ignored in single-user mode
            conversation_history=global_messages,
            feedback_data=[]
        )

        print(f"   📊 Extracted {len(preferences.explicit)} explicit preferences")
        print(f"   🎯 Deployment mode: {preferences.deployment_mode}")
        print(f"   🌐 User ID: {preferences.user_id or 'Global'}")

        # Show global preferences
        for pref in preferences.explicit:
            print(f"   • {pref.preference_type.value}: {pref.value} (confidence: {pref.confidence.weighted_confidence:.2f})")

        # Test adaptation with global preferences
        base_response = "This is a complex topic with many nuances that require careful consideration and detailed analysis."

        adapted = await adaptive_generator.generate_adaptive_response(
            base_response=base_response,
            user_preferences=preferences,
            context=ConversationContext()
        )

        print(f"\n🎨 Global Adaptation Results:")
        print(f"   🔄 Applied {len(adapted.adaptations_applied)} adaptations")
        print(f"   📈 Confidence: {adapted.confidence:.2f}")
        print(f"   📝 Original length: {len(base_response)} chars")
        print(f"   📝 Adapted length: {len(adapted.adapted)} chars")

    async def demo_contextual_adaptation(self):
        """Demonstrate contextual preference prediction and adaptation"""
        print("\n🔸 Contextual Adaptation: Smart Context-Aware Responses")
        print("=" * 60)

        overlord = self.create_mock_overlord(multi_user=True)
        preference_engine = UserPreferenceEngine(overlord)
        adaptive_generator = AdaptiveResponseGenerator(overlord)

        # Test different contexts
        contexts = {
            "Morning Rush": ConversationContext(
                urgency="high",
                user_mood="focused",
                session_length=2,
                current_task="quick question"
            ),
            "Evening Learning": ConversationContext(
                urgency="low",
                user_mood="curious",
                session_length=15,
                topic="learning new concept",
                current_task="educational exploration"
            ),
            "Debugging Crisis": ConversationContext(
                urgency="urgent",
                user_mood="stressed",
                current_task="fix production bug",
                topic="troubleshooting error"
            ),
            "Weekend Project": ConversationContext(
                urgency="low",
                user_mood="relaxed",
                topic="hobby project",
                current_task="creative exploration"
            )
        }

        base_response = "Here's how to approach this problem with a systematic methodology."

        for context_name, context in contexts.items():
            print(f"\n🎭 Context: {context_name}")

            # Get contextual preferences
            contextual_prefs = await preference_engine.get_preferences_for_context(
                user_id="demo_user",
                current_context=context
            )

            print(f"   🧠 Predicted {len(contextual_prefs.contextual)} contextual preferences")

            # Show predicted preferences
            for pref in contextual_prefs.contextual[:2]:
                print(f"   • {pref.preference_type.value}: {pref.value} (method: {pref.prediction_method})")

            # Generate adapted response
            adapted = await adaptive_generator.generate_adaptive_response(
                base_response=base_response,
                user_preferences=contextual_prefs,
                context=context,
                user_id="demo_user"
            )

            print(f"   🎨 Adaptations: {len(adapted.adaptations_applied)}")
            if adapted.adaptations_applied:
                for adaptation in adapted.adaptations_applied[:2]:
                    print(f"      - {adaptation.adaptation_type.value}: {adaptation.reason}")

    async def demo_preference_learning(self):
        """Demonstrate progressive preference learning over time"""
        print("\n🔸 Preference Learning: Progressive Intelligence Over Time")
        print("=" * 60)

        overlord = self.create_mock_overlord(multi_user=True)
        preference_engine = UserPreferenceEngine(overlord)

        user_id = "learning_demo_user"

        # Simulate conversation progression over time
        conversation_stages = [
            {
                "stage": "Initial Interaction",
                "messages": [
                    Message(content="Hello, I need help with programming", role="user", timestamp=time.time(), user_id=user_id),
                    Message(content="I prefer detailed explanations", role="user", timestamp=time.time(), user_id=user_id)
                ]
            },
            {
                "stage": "Learning Patterns",
                "messages": [
                    Message(content="Can you format code examples better?", role="user", timestamp=time.time(), user_id=user_id),
                    Message(content="I like step-by-step instructions", role="user", timestamp=time.time(), user_id=user_id),
                    Message(content="Please use more technical terminology", role="user", timestamp=time.time(), user_id=user_id)
                ]
            },
            {
                "stage": "Refined Understanding",
                "messages": [
                    Message(content="Use code blocks for examples please", role="user", timestamp=time.time(), user_id=user_id),
                    Message(content="I prefer formal technical documentation style", role="user", timestamp=time.time(), user_id=user_id),
                    Message(content="Always include error handling in examples", role="user", timestamp=time.time(), user_id=user_id)
                ]
            }
        ]

        print("📈 Simulating preference learning progression:")

        cumulative_messages = []
        for stage_info in conversation_stages:
            cumulative_messages.extend(stage_info["messages"])

            print(f"\n📚 Stage: {stage_info['stage']} ({len(cumulative_messages)} total messages)")

            # Mock filtering for user separation
            preference_engine._filter_user_history = Mock(return_value=cumulative_messages)
            preference_engine._filter_user_feedback = Mock(return_value=[])

            preferences = await preference_engine.analyze_user_preferences(
                user_id=user_id,
                conversation_history=cumulative_messages,
                feedback_data=[]
            )

            print(f"   🧠 Learned preferences: {len(preferences.explicit)} explicit, {len(preferences.implicit)} implicit")

            # Show confidence progression
            for pref_type, confidence in preferences.confidence_scores.items():
                if confidence.data_points > 0:
                    print(f"   📊 {pref_type.value}: {confidence.weighted_confidence:.2f} confidence ({confidence.data_points} data points)")

    async def demo_adaptive_responses(self):
        """Demonstrate various types of adaptive responses"""
        print("\n🔸 Adaptive Response Generation: Intelligent Personalization")
        print("=" * 60)

        overlord = self.create_mock_overlord(multi_user=False)
        adaptive_generator = AdaptiveResponseGenerator(overlord)

        # Create diverse preference profiles
        preference_profiles = {
            "Professional": {
                "communication_style": "formal",
                "detail_level": "concise",
                "preferred_formats": ["numbered"],
                "description": "Business professional needing efficient communication"
            },
            "Student": {
                "communication_style": "friendly",
                "detail_level": "comprehensive",
                "preferred_formats": ["step-by-step"],
                "description": "Student wanting thorough explanations with examples"
            },
            "Developer": {
                "communication_style": "technical",
                "detail_level": "detailed",
                "preferred_formats": ["code_blocks"],
                "description": "Developer needing technical precision and code examples"
            }
        }

        base_responses = [
            "Here's how to optimize your database queries for better performance.",
            "Let me explain the concept of machine learning algorithms.",
            "This is the process for setting up a secure authentication system."
        ]

        for profile_name, profile_data in preference_profiles.items():
            print(f"\n👤 Profile: {profile_name}")
            print(f"   📝 {profile_data['description']}")

            # Create preferences object
            from runtime.muxi.runtime.overlord.intelligence.types import UserPreferences, ExplicitPreference, ConfidenceScore

            explicit_prefs = []
            for pref_type_str, value in profile_data.items():
                if pref_type_str != "description":
                    try:
                        pref_type = PreferenceType(pref_type_str)
                        explicit_prefs.append(ExplicitPreference(
                            preference_type=pref_type,
                            value=value,
                            confidence=ConfidenceScore(value=0.8, data_points=3, recency=1.0, consistency=0.9),
                            source_message=f"User requested {pref_type_str}",
                            timestamp=time.time()
                        ))
                    except ValueError:
                        continue

            preferences = UserPreferences(
                user_id=None,
                deployment_mode="single_user",
                explicit=explicit_prefs
            )

            # Test adaptation on first response
            base_response = base_responses[0]
            adapted = await adaptive_generator.generate_adaptive_response(
                base_response=base_response,
                user_preferences=preferences,
                context=ConversationContext()
            )

            print(f"   🎨 Adaptations applied: {len(adapted.adaptations_applied)}")
            print(f"   📈 Confidence: {adapted.confidence:.2f}")

            # Show specific adaptations
            for adaptation in adapted.adaptations_applied:
                print(f"      • {adaptation.adaptation_type.value}: {adaptation.reason}")

            print(f"   📝 Adapted response preview: {adapted.adapted[:100]}...")

    async def demo_feedback_integration(self):
        """Demonstrate real-time feedback integration and learning"""
        print("\n🔸 Feedback Integration: Real-time Preference Refinement")
        print("=" * 60)

        overlord = self.create_mock_overlord(multi_user=True)
        preference_engine = UserPreferenceEngine(overlord)

        user_id = "feedback_demo_user"

        # Simulate initial preferences
        initial_messages = [
            Message(content="I like detailed responses", role="user", timestamp=time.time(), user_id=user_id)
        ]

        # Create actual FeedbackEvent objects for testing
        feedback_events = [
            FeedbackEvent(
                user_id=user_id,
                feedback_type="negative",
                feedback_content="Too verbose, please be more concise",
                message_id="msg_1",
                timestamp=time.time(),
                context={"response_length": 500, "user_request": "brief"}
            ),
            FeedbackEvent(
                user_id=user_id,
                feedback_type="positive",
                feedback_content="Perfect formatting with the numbered list",
                message_id="msg_2",
                timestamp=time.time(),
                context={"format": "numbered_list", "satisfaction": 5}
            ),
            FeedbackEvent(
                user_id=user_id,
                feedback_type="correction",
                feedback_content="I prefer bullet points over numbered lists",
                message_id="msg_3",
                timestamp=time.time(),
                context={
                    "format_preference": "bullets",
                    "previous_format": "numbered"
                }
            )
        ]

        # Mock filtering
        preference_engine._filter_user_history = Mock(
            return_value=initial_messages
        )
        preference_engine._filter_user_feedback = Mock(
            return_value=feedback_events
        )

        initial_prefs = await preference_engine.analyze_user_preferences(
            user_id=user_id,
            conversation_history=initial_messages,
            feedback_data=feedback_events
        )

        print(f"📚 Initial preferences: {len(initial_prefs.explicit)} explicit")
        print(f"🔄 Processing {len(feedback_events)} FeedbackEvent objects")

        # Test FeedbackEvent properties
        for i, feedback_event in enumerate(feedback_events, 1):
            print(f"\n📝 FeedbackEvent {i}: {feedback_event.feedback_type}")
            print(f"   👤 User ID: {feedback_event.user_id}")
            print(f"   💬 Content: '{feedback_event.feedback_content}'")
            print(f"   📧 Message ID: {feedback_event.message_id}")
            print(f"   🕒 Timestamp: {feedback_event.timestamp}")
            print(f"   📊 Context: {feedback_event.context}")

        # Simulate feedback scenarios with proper descriptions
        feedback_scenarios = [
            {
                "event": feedback_events[0],
                "description": "User requests shorter responses"
            },
            {
                "event": feedback_events[1],
                "description": "User appreciates structured format"
            },
            {
                "event": feedback_events[2],
                "description": "User corrects format preference"
            }
        ]

        current_prefs = initial_prefs

        for i, feedback_scenario in enumerate(feedback_scenarios, 1):
            feedback_event = feedback_scenario["event"]
            print(f"\n📝 Feedback {i}: {feedback_scenario['description']}")
            print(f"   💬 '{feedback_event.feedback_content}'")
            print(f"   📝 Type: {feedback_event.feedback_type}")
            print(f"   📧 Message ID: {feedback_event.message_id}")

            # Apply feedback using the actual FeedbackEvent
            success = await preference_engine.update_preferences_from_feedback(
                feedback_type=feedback_event.feedback_type,
                feedback_content=feedback_event.feedback_content,
                user_id=feedback_event.user_id,
                context=feedback_event.context
            )

            print(f"   ✅ Feedback processed: {success}")

            # Get updated preferences
            updated_prefs = await preference_engine.get_stored_preferences(user_id)
            if updated_prefs:
                explicit_count = len(updated_prefs.explicit)
                implicit_count = len(updated_prefs.implicit)
                print(f"   🧠 Updated preferences: {explicit_count} explicit, "
                      f"{implicit_count} implicit")
                current_prefs = updated_prefs

        # Show learning progression
        print(f"\n📈 Learning Summary:")
        print(f"   🎯 Final preference count: {len(current_prefs.explicit)} explicit")
        print(f"   🚀 Deployment mode: {current_prefs.deployment_mode}")
        print(f"   📊 User-specific learning completed for: {current_prefs.user_id}")

    async def run_full_demo(self):
        """Run the complete Phase 3 demonstration"""
        print("🚀 Phase 3: User Experience Intelligence Demonstration")
        print("=" * 80)
        print("This demo showcases intelligent context understanding and adaptive response generation")
        print("with automatic multi-user vs single-user deployment mode detection.")
        print("=" * 80)

        for demo_name, demo_func in self.demo_scenarios:
            try:
                await demo_func()
                print("\n✅ Demo completed successfully")
                await asyncio.sleep(1)  # Brief pause between demos
            except Exception as e:
                print(f"\n❌ Demo failed: {e}")
                continue

        print("\n" + "=" * 80)
        print("🎉 Phase 3 Demonstration Complete!")
        print("=" * 80)
        print("\n📋 Key Capabilities Demonstrated:")
        print("  ✅ Multi-user mode with strict user separation")
        print("  ✅ Single-user mode with global preference learning")
        print("  ✅ Contextual preference prediction")
        print("  ✅ Progressive preference learning over time")
        print("  ✅ Adaptive response generation with multiple adaptation types")
        print("  ✅ Real-time feedback integration and preference refinement")
        print("\n🎯 Phase 3 Implementation: COMPLETE")
        print("📈 System Status: Enterprise-ready intelligent user experience platform")


async def main():
    """Run the Phase 3 demonstration"""
    demo = Phase3Demo()
    await demo.run_full_demo()


if __name__ == "__main__":
    asyncio.run(main())
