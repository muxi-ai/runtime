#!/usr/bin/env python3
"""
Mock A2A Registry Server

A standalone development server that simulates external A2A (Agent-to-Agent)
registries for testing MUXI framework integration. This server:

- Accepts agent registrations from MUXI formations
- Provides hardcoded test agents with various authentication schemes
- Implements A2A-compliant discovery endpoints
- Enables testing of external registry integration

Usage:
    python runtime/runtime/muxi/runtime/utils/a2a_registry.py

The server will start on http://localhost:9090

This is a development-only tool and does not interfere with production runtime.
"""

import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Configuration
# =============================================================================

REGISTRY_CONFIG = {
    "host": "0.0.0.0",
    "port": 9090,
    "log_level": "info",
    "data_dir": ".registry_data",
    "max_agents": 1000,
    "agent_ttl_hours": 24,
}


# =============================================================================
# Pydantic Models for A2A AgentCard
# =============================================================================


class Provider(BaseModel):
    organization: str
    url: str


class Capabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False


class SecurityScheme(BaseModel):
    type: str
    scheme: Optional[str] = None
    bearerFormat: Optional[str] = None
    name: Optional[str] = None
    in_: Optional[str] = Field(None, alias="in")
    flows: Optional[Dict[str, Any]] = None


class Skill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str] = []


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str
    provider: Provider
    capabilities: Capabilities
    securitySchemes: Dict[str, SecurityScheme] = {}
    security: List[Dict[str, List[str]]] = []
    defaultInputModes: List[str] = ["application/json"]
    defaultOutputModes: List[str] = ["application/json"]
    skills: List[Skill] = []
    iconUrl: Optional[str] = None
    documentationUrl: Optional[str] = None
    supportsAuthenticatedExtendedCard: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class DiscoveryResponse(BaseModel):
    agents: List[AgentCard]
    total: int
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    version: str
    registered_agents: int
    uptime_seconds: float


# =============================================================================
# Hardcoded Test Agents
# =============================================================================

HARDCODED_AGENTS = [
    {
        "name": "external-billing-service",
        "description": "Third-party billing and payment processing with API key auth",
        "url": "https://billing-service.vendor.com/a2a",
        "version": "2.1.0",
        "provider": {
            "organization": "Billing Solutions Inc",
            "url": "https://billing-service.vendor.com",
        },
        "capabilities": {"streaming": True, "pushNotifications": False},
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        "security": [{"ApiKeyAuth": []}],
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "payment-processing",
                "name": "Payment Processing",
                "description": "Process credit card and ACH payments",
                "tags": ["billing", "payments", "credit-card", "ach"],
            },
            {
                "id": "invoice-generation",
                "name": "Invoice Generation",
                "description": "Generate PDF invoices and receipts",
                "tags": ["billing", "invoices", "pdf"],
            },
        ],
    },
    {
        "name": "analytics-engine",
        "description": "Data analytics and reporting service with Bearer token auth",
        "url": "https://analytics.vendor-x.io/a2a",
        "version": "1.5.3",
        "provider": {"organization": "AnalyticsX Corporation", "url": "https://vendor-x.io"},
        "capabilities": {"streaming": True, "pushNotifications": True},
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
        "security": [{"BearerAuth": []}],
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": "data-analysis",
                "name": "Data Analysis",
                "description": "Statistical analysis and data insights",
                "tags": ["analytics", "statistics", "insights"],
            },
            {
                "id": "report-generation",
                "name": "Report Generation",
                "description": "Generate business intelligence reports",
                "tags": ["analytics", "reports", "business-intelligence"],
            },
        ],
    },
    {
        "name": "notification-hub",
        "description": "Multi-channel notification service with OAuth2 auth",
        "url": "https://notify.cloudservice.net/a2a",
        "version": "3.0.1",
        "provider": {
            "organization": "CloudService Notifications",
            "url": "https://cloudservice.net",
        },
        "capabilities": {"streaming": False, "pushNotifications": True},
        "securitySchemes": {
            "OAuth2": {
                "type": "oauth2",
                "flows": {
                    "clientCredentials": {
                        "tokenUrl": "https://auth.cloudservice.net/oauth/token",
                        "scopes": {
                            "notifications:send": "Send notifications",
                            "notifications:read": "Read notification status",
                        },
                    }
                },
            }
        },
        "security": [{"OAuth2": ["notifications:send"]}],
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "email-notifications",
                "name": "Email Notifications",
                "description": "Send email notifications and campaigns",
                "tags": ["notifications", "email", "campaigns"],
            },
            {
                "id": "sms-notifications",
                "name": "SMS Notifications",
                "description": "Send SMS and text message notifications",
                "tags": ["notifications", "sms", "text-messaging"],
            },
        ],
    },
    {
        "name": "document-processor",
        "description": "Document processing service with Basic auth",
        "url": "https://docs.enterprise-tools.com/a2a",
        "version": "4.2.0",
        "provider": {"organization": "Enterprise Tools Inc", "url": "https://enterprise-tools.com"},
        "capabilities": {"streaming": True, "pushNotifications": False},
        "securitySchemes": {"BasicAuth": {"type": "http", "scheme": "basic"}},
        "security": [{"BasicAuth": []}],
        "defaultInputModes": ["application/json", "application/pdf", "text/plain"],
        "defaultOutputModes": ["application/json", "application/pdf"],
        "skills": [
            {
                "id": "pdf-processing",
                "name": "PDF Processing",
                "description": "Extract text and data from PDF documents",
                "tags": ["documents", "pdf", "extraction"],
            },
            {
                "id": "ocr-scanning",
                "name": "OCR Scanning",
                "description": "Optical character recognition for scanned documents",
                "tags": ["documents", "ocr", "scanning"],
            },
        ],
    },
    {
        "name": "public-data-service",
        "description": "Public data service with no authentication required",
        "url": "https://public-api.data-commons.org/a2a",
        "version": "1.0.0",
        "provider": {"organization": "Data Commons Foundation", "url": "https://data-commons.org"},
        "capabilities": {"streaming": False, "pushNotifications": False},
        "securitySchemes": {},
        "security": [],
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/csv"],
        "skills": [
            {
                "id": "weather-data",
                "name": "Weather Data",
                "description": "Current and historical weather information",
                "tags": ["weather", "public-data", "meteorology"],
            },
            {
                "id": "geographic-info",
                "name": "Geographic Information",
                "description": "Geographic and demographic data",
                "tags": ["geography", "demographics", "public-data"],
            },
        ],
    },
]


# =============================================================================
# Registry Storage
# =============================================================================


class RegistryStorage:
    """Simple JSON file-based storage for registered agents."""

    def __init__(self, data_dir: str = ".registry_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.agents_file = self.data_dir / "agents.json"
        self.start_time = time.time()

        # Initialize storage file if it doesn't exist
        if not self.agents_file.exists():
            self._save_agents({})

    def _load_agents(self) -> Dict[str, Dict]:
        """Load registered agents from storage."""
        try:
            with open(self.agents_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_agents(self, agents: Dict[str, Dict]):
        """Save registered agents to storage."""
        with open(self.agents_file, "w") as f:
            json.dump(agents, f, indent=2)

    def register_agent(self, agent_card: AgentCard) -> bool:
        """Register a new agent. Returns True if successful."""
        agents = self._load_agents()

        # Use URL as unique key
        url_key = agent_card.url

        # Add registration metadata
        agent_data = agent_card.model_dump()
        agent_data["_registered_at"] = datetime.now(timezone.utc).isoformat()

        agents[url_key] = agent_data
        self._save_agents(agents)

        logging.info(f"Registered agent: {agent_card.name} at {agent_card.url}")
        return True

    def deregister_agent(self, agent_url: str) -> bool:
        """Deregister an agent by URL. Returns True if found and removed."""
        agents = self._load_agents()

        if agent_url in agents:
            agent_name = agents[agent_url].get("name", "unknown")
            del agents[agent_url]
            self._save_agents(agents)
            logging.info(f"Deregistered agent: {agent_name} at {agent_url}")
            return True

        return False

    def get_registered_agents(self) -> List[AgentCard]:
        """Get all registered agents as AgentCard objects."""
        agents = self._load_agents()
        agent_cards = []

        for agent_data in agents.values():
            # Remove metadata before creating AgentCard
            clean_data = {k: v for k, v in agent_data.items() if not k.startswith("_")}
            try:
                agent_cards.append(AgentCard(**clean_data))
            except Exception as e:
                logging.warning(f"Failed to parse stored agent: {e}")

        return agent_cards

    def get_uptime(self) -> float:
        """Get server uptime in seconds."""
        return time.time() - self.start_time


# =============================================================================
# FastAPI Application
# =============================================================================

# Initialize FastAPI app
app = FastAPI(
    title="Mock A2A Registry Server",
    description="Development server for testing A2A registry integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Initialize storage
storage = RegistryStorage(REGISTRY_CONFIG["data_dir"])

# Setup logging
logging.basicConfig(
    level=getattr(logging, REGISTRY_CONFIG["log_level"].upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# API Endpoints
# =============================================================================


@app.post("/register", status_code=201)
async def register_agent(agent_card: AgentCard):
    """
    Register an agent with the registry.

    Accepts a standard A2A AgentCard and stores it for discovery.
    """
    try:
        # Check if we're at capacity
        current_agents = len(storage.get_registered_agents())
        if current_agents >= REGISTRY_CONFIG["max_agents"]:
            max_agents = REGISTRY_CONFIG["max_agents"]
            raise HTTPException(
                status_code=429, detail=f"Registry at capacity ({max_agents} agents)"
            )

        success = storage.register_agent(agent_card)
        if success:
            return {
                "message": "Agent registered successfully",
                "agent_url": agent_card.url,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to register agent")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/register/{agent_url_encoded}")
async def deregister_agent(agent_url_encoded: str):
    """
    Deregister an agent from the registry.

    The agent URL must be URL-encoded in the path parameter.
    """
    try:
        # Decode the URL
        agent_url = urllib.parse.unquote(agent_url_encoded)

        success = storage.deregister_agent(agent_url)
        if success:
            return {
                "message": "Agent deregistered successfully",
                "agent_url": agent_url,
                "deregistered_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_url}")

    except Exception as e:
        logger.error(f"Error deregistering agent: {e}")
        raise HTTPException(status_code=500, detail="Failed to deregister agent")


@app.get("/discover", response_model=DiscoveryResponse)
async def discover_agents(
    capabilities: Optional[str] = Query(None, description="Comma-separated capabilities filter"),
    skills: Optional[str] = Query(None, description="Comma-separated skills filter"),
    provider: Optional[str] = Query(None, description="Provider organization filter"),
):
    """
    Discover agents based on query parameters.

    Returns both hardcoded test agents and registered agents.
    Supports filtering by capabilities, skills, and provider.
    """
    try:
        # Get all agents (hardcoded + registered)
        all_agents = []

        # Add hardcoded test agents
        for agent_data in HARDCODED_AGENTS:
            all_agents.append(AgentCard(**agent_data))

        # Add registered agents
        all_agents.extend(storage.get_registered_agents())

        # Apply filters
        filtered_agents = all_agents

        if capabilities:
            capability_list = [c.strip().lower() for c in capabilities.split(",")]
            filtered_agents = [
                agent
                for agent in filtered_agents
                if any(
                    capability in [skill.id.lower() for skill in agent.skills]
                    or capability in [tag.lower() for skill in agent.skills for tag in skill.tags]
                    for capability in capability_list
                )
            ]

        if skills:
            skill_list = [s.strip().lower() for s in skills.split(",")]
            filtered_agents = [
                agent
                for agent in filtered_agents
                if any(
                    skill in [agent_skill.id.lower() for agent_skill in agent.skills]
                    or skill
                    in [tag.lower() for agent_skill in agent.skills for tag in agent_skill.tags]
                    for skill in skill_list
                )
            ]

        if provider:
            provider_filter = provider.strip().lower()
            filtered_agents = [
                agent
                for agent in filtered_agents
                if provider_filter in agent.provider.organization.lower()
            ]

        logger.info(
            f"Discovery query returned {len(filtered_agents)} agents "
            f"(capabilities={capabilities}, skills={skills}, provider={provider})"
        )

        return DiscoveryResponse(
            agents=filtered_agents,
            total=len(filtered_agents),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Error during discovery: {e}")
        raise HTTPException(status_code=500, detail="Failed to discover agents")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns server status and basic metrics.
    """
    try:
        registered_count = len(storage.get_registered_agents())
        uptime = storage.get_uptime()

        return HealthResponse(
            status="healthy",
            version="1.0.0",
            registered_agents=registered_count,
            uptime_seconds=uptime,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy", version="1.0.0", registered_agents=0, uptime_seconds=0
        )


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    """Main entry point for standalone execution."""
    print("🚀 Starting Mock A2A Registry Server...")
    print(f"📍 Server will run on http://{REGISTRY_CONFIG['host']}:{REGISTRY_CONFIG['port']}")
    print(f"📊 API docs available at http://localhost:{REGISTRY_CONFIG['port']}/docs")
    print(f"🗄️  Data directory: {REGISTRY_CONFIG['data_dir']}")
    print(f"🧪 Hardcoded test agents: {len(HARDCODED_AGENTS)}")

    # Initialize storage and log startup info
    logger.info("Mock A2A Registry Server starting up...")
    logger.info(f"Data directory: {REGISTRY_CONFIG['data_dir']}")
    logger.info(f"Hardcoded test agents: {len(HARDCODED_AGENTS)}")

    print()
    print("Available endpoints:")
    print("  POST   /register          - Register an agent")
    print("  DELETE /register/{url}    - Deregister an agent")
    print("  GET    /discover          - Discover agents")
    print("  GET    /health            - Health check")
    print()
    print("Example usage:")
    print("  curl http://localhost:9090/health")
    print("  curl http://localhost:9090/discover?capabilities=billing")
    print()

    # Run the server
    uvicorn.run(
        app,
        host=REGISTRY_CONFIG["host"],
        port=REGISTRY_CONFIG["port"],
        log_level=REGISTRY_CONFIG["log_level"],
        access_log=True,
    )


if __name__ == "__main__":
    main()
