#!/usr/bin/env python3
"""
Agent Collaboration Infrastructure Example

This example demonstrates the comprehensive agent collaboration capabilities
in the MUXI framework, including:

1. Expertise Registration and Discovery
2. Consultation Requests
3. Information Sharing
4. Peer Coordination
5. Collaboration Statistics

The collaboration system enables tactical peer-to-peer communication while
preserving the overlord's strategic coordination role.
"""

import asyncio
import sys
import os

# Handle imports with path management
try:
    from muxi.runtime.overlord import Overlord
except ImportError:
    # Add the runtime directory to the Python path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))
    from muxi.runtime.overlord import Overlord


class MockLLM:
    """Mock LLM that provides context-aware responses for different agent types."""

    def __init__(self, agent_type="general"):
        self.agent_type = agent_type
        self.call_count = 0

    async def chat(self, messages):
        """Generate responses based on agent type and message content."""
        self.call_count += 1

        if not messages:
            return f"Mock response from {self.agent_type} agent"

        last_message = messages[-1].get('content', '').lower()

        # Handle consultation requests
        if 'consultation request' in last_message:
            if self.agent_type == "security":
                return (
                    "Based on my cybersecurity expertise, here are the key "
                    "recommendations:\n\n"
                    "1. Implement multi-factor authentication (MFA)\n"
                    "2. Use HTTPS with TLS 1.3 for all communications\n"
                    "3. Validate and sanitize all user inputs\n"
                    "4. Implement proper session management\n"
                    "5. Use rate limiting to prevent abuse\n"
                    "6. Regular security audits and penetration testing\n\n"
                    "These practices will significantly improve your API security posture."
                )

            elif self.agent_type == "data":
                return (
                    "From a data analysis perspective, here's my advice:\n\n"
                    "1. Ensure data quality with validation pipelines\n"
                    "2. Implement proper data lineage tracking\n"
                    "3. Use statistical methods for outlier detection\n"
                    "4. Consider data privacy regulations (GDPR, CCPA)\n"
                    "5. Implement proper backup and recovery procedures\n"
                    "6. Use version control for data schemas\n\n"
                    "These approaches will help maintain data integrity and reliability."
                )

        # Handle coordination requests
        elif 'coordination request' in last_message:
            if 'handoff' in last_message:
                return (
                    f"Task handoff acknowledged by {self.agent_type} agent. "
                    "Ready to proceed with next phase."
                )
            elif 'sync' in last_message:
                return (
                    f"Synchronization confirmed by {self.agent_type} agent. "
                    "Status: ready for coordinated action."
                )
            elif 'parallel' in last_message:
                return (
                    f"Parallel coordination established by {self.agent_type} agent. "
                    "Working in parallel mode."
                )

        # Handle general messages
        elif 'security' in last_message:
            return (
                "Security recommendation: Always follow the principle of "
                "least privilege and defense in depth."
            )
        elif 'data' in last_message:
            return (
                "Data analysis insight: Clean data is the foundation of "
                "reliable analytics."
            )
        elif 'deploy' in last_message:
            return (
                "Deployment guidance: Use blue-green deployments for "
                "zero-downtime releases."
            )

        return (
            f"General response from {self.agent_type} agent: "
            "Understood and ready to assist."
        )


async def demonstrate_agent_collaboration():
    """Demonstrate the complete agent collaboration infrastructure."""

    print("🤝 MUXI Agent Collaboration Infrastructure Demo")
    print("=" * 60)

    # Initialize overlord
    overlord = Overlord()

    # Create specialized agents with different expertise
    print("\n📋 Creating Specialized Agents...")

    security_agent = overlord.create_agent(
        agent_id="security-expert",
        model=MockLLM("security"),
        system_message=(
            "You are a cybersecurity expert specializing in application "
            "security, network security, and threat analysis."
        ),
        a2a_internal=True
    )

    data_agent = overlord.create_agent(
        agent_id="data-scientist",
        model=MockLLM("data"),
        system_message=(
            "You are a data scientist specializing in machine learning, "
            "data analysis, and statistical modeling."
        ),
        a2a_internal=True
    )

    deployment_agent = overlord.create_agent(
        agent_id="devops-specialist",
        model=MockLLM("deployment"),
        system_message=(
            "You are a DevOps specialist focusing on deployment, "
            "infrastructure, and monitoring."
        ),
        a2a_internal=True
    )

    research_agent = overlord.create_agent(
        agent_id="research-coordinator",
        model=MockLLM("research"),
        system_message=(
            "You are a research coordinator who gathers and synthesizes "
            "information from multiple sources."
        ),
        a2a_internal=True
    )

    print(f"✅ Created {len(overlord.list_agents())} agents")

    # 1. EXPERTISE REGISTRATION
    print("\n🎓 Step 1: Registering Agent Expertise...")

    # Register security expertise
    await security_agent.register_expertise(
        expertise_areas=[
            "cybersecurity", "penetration_testing",
            "security_auditing", "threat_analysis"
        ],
        proficiency_levels={
            "cybersecurity": "expert",
            "penetration_testing": "master",
            "security_auditing": "expert",
            "threat_analysis": "expert"
        }
    )
    print(
        "  🔒 Security Expert: Registered cybersecurity, penetration testing, "
        "security auditing, threat analysis"
    )

    # Register data science expertise
    await data_agent.register_expertise(
        expertise_areas=[
            "machine_learning", "data_analysis",
            "statistical_modeling", "data_visualization"
        ],
        proficiency_levels={
            "machine_learning": "expert",
            "data_analysis": "master",
            "statistical_modeling": "expert",
            "data_visualization": "intermediate"
        }
    )
    print(
        "  📊 Data Scientist: Registered machine learning, data analysis, "
        "statistical modeling, data visualization"
    )

    # Register DevOps expertise
    await deployment_agent.register_expertise(
        expertise_areas=["kubernetes", "docker", "ci_cd", "monitoring", "infrastructure"],
        proficiency_levels={
            "kubernetes": "expert",
            "docker": "master",
            "ci_cd": "expert",
            "monitoring": "intermediate",
            "infrastructure": "expert"
        }
    )
    print("  🚀 DevOps Specialist: Registered kubernetes, docker, CI/CD, monitoring, infrastructure")

    # Register research expertise
    await research_agent.register_expertise(
        expertise_areas=["research_methodology", "information_synthesis", "trend_analysis"],
        proficiency_levels={
            "research_methodology": "expert",
            "information_synthesis": "master",
            "trend_analysis": "intermediate"
        }
    )
    print("  🔬 Research Coordinator: Registered research methodology, information synthesis, trend analysis")

    # 2. EXPERTISE DISCOVERY
    print("\n🔍 Step 2: Discovering Experts...")

    # Research agent looks for security experts
    security_experts = await research_agent.find_expert(
        topic="security",
        min_proficiency="expert"
    )
    print("  🔍 Found {} security experts:".format(len(security_experts)))
    for expert_id, info in security_experts.items():
        print("    - {}: {} in {}".format(
            expert_id, info['proficiency'], info['expertise_areas']
        ))

    # Security agent looks for data analysis experts
    data_experts = await security_agent.find_expert(
        topic="data_analysis",
        min_proficiency="intermediate"
    )
    print("  🔍 Found {} data analysis experts:".format(len(data_experts)))
    for expert_id, info in data_experts.items():
        print("    - {}: {} in {}".format(
            expert_id, info['proficiency'], info['expertise_areas']
        ))

    # 3. CONSULTATION REQUESTS
    print("\n💭 Step 3: Agent Consultation...")

    # Research agent consults security expert about API security
    print("  📞 Research agent consulting security expert about API security...")
    consultation_response = await research_agent.request_consultation(
        target_agent_id="security-expert",
        topic="API security best practices",
        context={
            "project": "user-management-system",
            "current_stack": "Python FastAPI",
            "user_count": "10000+"
        }
    )

    if consultation_response and consultation_response.get("status") == "success":
        print("  ✅ Consultation successful!")
        response_text = consultation_response["response"]
        # Show first 200 characters of response
        print(f"  💡 Expert advice: {response_text[:200]}...")
        print(f"  👨‍💼 Expert: {consultation_response.get('expert_agent')}")
        print(f"  📋 Topic: {consultation_response.get('consultation_topic')}")
    else:
        print("  ❌ Consultation failed")

    # 4. INFORMATION SHARING
    print("\n📢 Step 4: Information Sharing...")

    # Security agent shares threat intelligence with data agent
    print("  📤 Security expert sharing threat intelligence...")
    share_success = await security_agent.share_information(
        target_agent_id="data-scientist",
        information="New ML-based attack pattern detected: adversarial examples targeting image classification models. Affects TensorFlow and PyTorch models with specific vulnerability in input preprocessing.",
        topic="security_threats",
        relevance_reason="You work with ML models and should be aware of these emerging threats"
    )

    if share_success:
        print("  ✅ Information shared successfully!")
        print("  📋 Topic: security_threats")
        print("  🎯 Relevance: ML security concerns")
    else:
        print("  ❌ Information sharing failed")

    # Data agent shares research findings with deployment agent
    print("  📤 Data scientist sharing performance insights...")
    share_success2 = await data_agent.share_information(
        target_agent_id="devops-specialist",
        information="Analysis shows 40% performance improvement when using async processing for batch jobs. Recommend implementing async patterns in the deployment pipeline.",
        topic="performance_optimization",
        relevance_reason="Performance insights relevant to your deployment strategies"
    )

    if share_success2:
        print("  ✅ Performance insights shared!")
        print("  📋 Topic: performance_optimization")
        print("  🎯 Relevance: Deployment optimization")

    # 5. PEER COORDINATION
    print("\n🔄 Step 5: Peer Coordination...")

    # Data agent coordinates handoff to deployment agent
    print("  🔄 Data scientist coordinating task handoff with DevOps...")
    coordination_response = await data_agent.coordinate_with_peer(
        peer_agent_id="devops-specialist",
        coordination_type="handoff",
        details={
            "task": "ML model validation complete",
            "next_step": "production_deployment",
            "artifacts": [
                "trained_model.pkl",
                "validation_results.json",
                "performance_metrics.csv",
                "deployment_config.yaml"
            ],
            "requirements": "GPU-enabled nodes, 8GB RAM minimum",
            "notes": "Model achieves 94.2% accuracy on test set"
        }
    )

    if coordination_response and coordination_response.get("status") == "success":
        print("  ✅ Task handoff coordinated successfully!")
        print(f"  🔄 Coordination type: {coordination_response.get('coordination_type')}")
        response_text = coordination_response["response"]
        print(f"  💬 Response: {response_text[:150]}...")
    else:
        print("  ❌ Coordination failed")

    # Security and deployment agents coordinate parallel work
    print("  🔄 Security and DevOps coordinating parallel security hardening...")
    parallel_coordination = await security_agent.coordinate_with_peer(
        peer_agent_id="devops-specialist",
        coordination_type="parallel",
        details={
            "work_area": "security_hardening",
            "dependencies": ["ssl_certificates", "firewall_rules", "monitoring_setup"],
            "timeline": "2_weeks",
            "sync_points": ["week_1_review", "final_security_audit"]
        }
    )

    if parallel_coordination and parallel_coordination.get("status") == "success":
        print("  ✅ Parallel coordination established!")
        print(f"  ⚡ Working in parallel on: security_hardening")
        print(f"  📅 Sync points: week_1_review, final_security_audit")

    # 6. COLLABORATION STATISTICS
    print("\n📊 Step 6: Collaboration Statistics...")

    stats = overlord.get_collaboration_stats()
    print(f"  👥 Total agents: {stats['total_agents']}")
    print(f"  🎓 Agents with expertise: {stats['agents_with_expertise']}")
    print(f"  📚 Total expertise areas: {stats['total_expertise_areas']}")

    print("\n  🏆 Most common expertise areas:")
    for expertise in stats["most_common_expertise"][:5]:  # Top 5
        print(f"    - {expertise['area']}: {expertise['agent_count']} agents")

    print("\n  📋 Expertise by agent:")
    for agent_id, agent_stats in stats["expertise_by_agent"].items():
        print(f"    - {agent_id}: {agent_stats['areas']} areas, proficiencies: {agent_stats['proficiencies']}")

    # 7. COLLABORATION WORKFLOW DEMONSTRATION
    print("\n🔄 Step 7: Complete Collaboration Workflow...")
    print("  Simulating a realistic multi-agent collaboration scenario...")

    # Scenario: Research agent coordinates a security assessment project
    print("\n  📋 Scenario: Multi-Agent Security Assessment Project")
    print("  " + "-" * 50)

    # Research agent finds experts for the project
    security_experts = await research_agent.find_expert("security", "expert")
    data_experts = await research_agent.find_expert("data_analysis", "intermediate")

    print(f"  🔍 Research coordinator found {len(security_experts)} security experts and {len(data_experts)} data experts")

    # Consultation phase
    if security_experts:
        expert_id = list(security_experts.keys())[0]
        consultation = await research_agent.request_consultation(
            target_agent_id=expert_id,
            topic="Security assessment methodology",
            context={
                "project": "enterprise_security_audit",
                "scope": "full_infrastructure",
                "timeline": "4_weeks"
            }
        )
        print(f"  💭 Consulted {expert_id} for security assessment methodology")

    # Information sharing phase
    await research_agent.share_information(
        target_agent_id="security-expert",
        information="Latest threat intelligence indicates increased targeting of API endpoints. Focus assessment on API security.",
        topic="threat_intelligence",
        relevance_reason="Critical for current security assessment project"
    )
    print("  📢 Shared threat intelligence with security expert")

    # Coordination phase
    coordination = await research_agent.coordinate_with_peer(
        peer_agent_id="security-expert",
        coordination_type="sync",
        details={
            "sync_point": "week_2_checkpoint",
            "deliverables": ["vulnerability_scan_results", "risk_assessment"],
            "next_steps": "remediation_planning"
        }
    )
    print("  🔄 Established coordination checkpoint with security expert")

    print("\n🎉 Agent Collaboration Demo Complete!")
    print("=" * 60)
    print("\nKey Features Demonstrated:")
    print("  ✅ Expertise registration and discovery")
    print("  ✅ Consultation requests between agents")
    print("  ✅ Proactive information sharing")
    print("  ✅ Peer coordination (handoff, sync, parallel)")
    print("  ✅ Collaboration analytics and statistics")
    print("  ✅ Complete multi-agent workflow")

    print("\nThis collaboration infrastructure enables:")
    print("  🎯 Tactical peer-to-peer communication")
    print("  🧠 Knowledge sharing and expertise discovery")
    print("  🔄 Coordinated multi-agent workflows")
    print("  📊 Collaboration monitoring and analytics")
    print("  🏗️ Scalable agent formation management")


if __name__ == "__main__":
    asyncio.run(demonstrate_agent_collaboration())
