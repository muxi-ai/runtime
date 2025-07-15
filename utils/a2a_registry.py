#!/usr/bin/env python3
"""
Mock A2A Registry Server

A standalone development server that simulates external A2A (Agent-to-Agent)
registries for testing MUXI framework integration. This server:

- Accepts agent registrations from MUXI formations using Google A2A protocol
- Provides hardcoded test agents in A2A-compliant format
- Implements A2A-compliant discovery endpoints
- Enables testing of external registry integration

Usage:
    python runtime/src/muxi/runtime/utils/a2a_registry.py

The server will start on http://localhost:9090

NOTE: WE DO NOT NEED TO USE OBSERVABILITY HERE!
This is a development-only tool and does not interfere with production runtime.
"""

import json

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .user_dirs import get_a2a_registry_dir
except ImportError:
    # When running as standalone script
    from user_dirs import get_a2a_registry_dir
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

import logging


# =============================================================================
# Configuration
# =============================================================================

REGISTRY_CONFIG = {
    "host": "0.0.0.0",
    "port": 9090,
    "log_level": "info",
    "data_dir": get_a2a_registry_dir(),
    "max_agents": 1000,
    "agent_ttl_hours": 24,
}


# =============================================================================
# Google A2A Protocol Models
# =============================================================================


class A2AAuthentication(BaseModel):
    """A2A Authentication configuration"""

    type: str  # "none", "bearer", "apiKey", "oauth2"
    description: Optional[str] = None
    required: bool = False


class A2ACapability(BaseModel):
    """A2A Capability definition"""

    name: str
    description: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class A2AEndpoint(BaseModel):
    """A2A Endpoint definition"""

    url: str
    methods: List[str] = Field(default_factory=lambda: ["POST"])
    description: Optional[str] = None


class AgentCard(BaseModel):
    """
    Google A2A Protocol AgentCard

    This follows the official Google A2A Agent Card specification.
    """

    # Required fields
    name: str
    description: str
    version: str
    url: str

    # A2A Protocol fields
    a2aVersion: str = "1.0"
    capabilities: Dict[str, A2ACapability] = Field(default_factory=dict)
    authentication: Optional[A2AAuthentication] = None
    endpoints: Dict[str, A2AEndpoint] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Optional fields
    iconUrl: Optional[str] = None
    documentationUrl: Optional[str] = None

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
# Hardcoded Test Agents (Google A2A Format)
# =============================================================================

HARDCODED_AGENTS = [
    {
        "name": "external-billing-service",
        "description": "Handles billing, invoicing, and payment processing for external services",
        "version": "2.1.0",
        "url": "https://billing-service.vendor.com/a2a",
        "a2aVersion": "1.0",
        "capabilities": {
            "payment_processing": {
                "name": "payment_processing",
                "description": "Process payments and handle billing operations",
                "enabled": True,
            },
            "invoice_generation": {
                "name": "invoice_generation",
                "description": "Generate and manage invoices",
                "enabled": True,
            },
        },
        "authentication": {
            "type": "apiKey",
            "description": "API key authentication for billing operations",
            "required": True,
        },
        "metadata": {
            "organization": "VendorCorp",
            "contact": "billing-support@vendor.com",
            "tags": ["billing", "payments", "finance"],
        },
    },
    {
        "name": "analytics-engine",
        "description": "Data analytics and reporting service",
        "url": "https://analytics.vendor-x.io/a2a",
        "version": "1.5.3",
        "a2aVersion": "1.0",
        "capabilities": {
            "data_analysis": {
                "name": "data_analysis",
                "description": "Statistical analysis and data insights",
                "enabled": True,
                "metadata": {"analysis_types": ["statistical", "predictive", "descriptive"]},
            },
            "report_generation": {
                "name": "report_generation",
                "description": "Generate business intelligence reports",
                "enabled": True,
                "metadata": {"formats": ["pdf", "html", "excel"]},
            },
            "streaming": {
                "name": "streaming",
                "description": "Real-time data streaming",
                "enabled": True,
                "metadata": {"protocols": ["websocket", "sse"]},
            },
        },
        "authentication": {
            "type": "bearer",
            "description": "JWT Bearer token authentication",
            "required": True,
        },
        "endpoints": {
            "analyze_data": {
                "url": "https://analytics.vendor-x.io/a2a/analyze",
                "methods": ["POST"],
                "description": "Analyze provided data",
            },
            "generate_report": {
                "url": "https://analytics.vendor-x.io/a2a/report",
                "methods": ["POST"],
                "description": "Generate analytical report",
            },
        },
        "metadata": {
            "organization": "AnalyticsX Corporation",
            "tags": ["analytics", "statistics", "reporting"],
            "support_email": "support@vendor-x.io",
        },
    },
    {
        "name": "notification-hub",
        "description": "Multi-channel notification service",
        "url": "https://notify.cloudservice.net/a2a",
        "version": "3.0.1",
        "a2aVersion": "1.0",
        "capabilities": {
            "email_notifications": {
                "name": "email_notifications",
                "description": "Send email notifications and campaigns",
                "enabled": True,
                "metadata": {"templates": ["plain", "html", "rich"]},
            },
            "sms_notifications": {
                "name": "sms_notifications",
                "description": "Send SMS and text message notifications",
                "enabled": True,
                "metadata": {"regions": ["US", "EU", "APAC"]},
            },
            "push_notifications": {
                "name": "push_notifications",
                "description": "Mobile and web push notifications",
                "enabled": True,
                "metadata": {"platforms": ["ios", "android", "web"]},
            },
        },
        "authentication": {
            "type": "oauth2",
            "description": "OAuth2 client credentials flow",
            "required": True,
        },
        "endpoints": {
            "send_email": {
                "url": "https://notify.cloudservice.net/a2a/email",
                "methods": ["POST"],
                "description": "Send email notification",
            },
            "send_sms": {
                "url": "https://notify.cloudservice.net/a2a/sms",
                "methods": ["POST"],
                "description": "Send SMS notification",
            },
        },
        "metadata": {
            "organization": "CloudService Notifications",
            "tags": ["notifications", "messaging", "communications"],
            "support_email": "support@cloudservice.net",
        },
    },
    {
        "name": "document-processor",
        "description": "Document processing and OCR service",
        "url": "https://docs.enterprise-tools.com/a2a",
        "version": "4.2.0",
        "a2aVersion": "1.0",
        "capabilities": {
            "pdf_processing": {
                "name": "pdf_processing",
                "description": "Extract text and data from PDF documents",
                "enabled": True,
                "metadata": {"max_file_size": "50MB", "supported_versions": ["1.4", "1.7", "2.0"]},
            },
            "ocr_scanning": {
                "name": "ocr_scanning",
                "description": "Optical character recognition for scanned documents",
                "enabled": True,
                "metadata": {"languages": ["en", "es", "fr", "de"], "accuracy": "95%"},
            },
            "document_conversion": {
                "name": "document_conversion",
                "description": "Convert between document formats",
                "enabled": True,
                "metadata": {"formats": ["pdf", "docx", "txt", "html"]},
            },
        },
        "authentication": {
            "type": "apiKey",
            "description": "API key authentication for document processing",
            "required": True,
        },
        "endpoints": {
            "process_pdf": {
                "url": "https://docs.enterprise-tools.com/a2a/pdf",
                "methods": ["POST"],
                "description": "Process PDF document",
            },
            "ocr_scan": {
                "url": "https://docs.enterprise-tools.com/a2a/ocr",
                "methods": ["POST"],
                "description": "Perform OCR on document",
            },
        },
        "metadata": {
            "organization": "Enterprise Tools Inc",
            "tags": ["documents", "pdf", "ocr", "conversion"],
            "support_email": "support@enterprise-tools.com",
        },
    },
    {
        "name": "public-data-service",
        "description": "Public data service with open access",
        "url": "https://public-api.data-commons.org/a2a",
        "version": "1.0.0",
        "a2aVersion": "1.0",
        "capabilities": {
            "weather_data": {
                "name": "weather_data",
                "description": "Current and historical weather information",
                "enabled": True,
                "metadata": {"coverage": "global", "history": "10_years"},
            },
            "geographic_info": {
                "name": "geographic_info",
                "description": "Geographic and demographic data",
                "enabled": True,
                "metadata": {"resolution": "city_level", "data_sources": ["census", "satellite"]},
            },
            "public_datasets": {
                "name": "public_datasets",
                "description": "Access to curated public datasets",
                "enabled": True,
                "metadata": {"categories": ["economic", "social", "environmental"]},
            },
        },
        "authentication": {
            "type": "none",
            "description": "No authentication required",
            "required": False,
        },
        "endpoints": {
            "get_weather": {
                "url": "https://public-api.data-commons.org/a2a/weather",
                "methods": ["GET", "POST"],
                "description": "Get weather data",
            },
            "get_geography": {
                "url": "https://public-api.data-commons.org/a2a/geography",
                "methods": ["GET", "POST"],
                "description": "Get geographic information",
            },
        },
        "metadata": {
            "organization": "Data Commons Foundation",
            "tags": ["public-data", "weather", "geography", "open-access"],
            "support_email": "support@data-commons.org",
        },
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

        # Ensure agents.json file exists with empty dict
        if not self.agents_file.exists():
            with open(self.agents_file, "w") as f:
                json.dump({}, f)

    def _load_agents(self) -> Dict[str, Dict]:
        """Load registered agents from storage."""
        try:
            with open(self.agents_file, "r") as f:
                agents = json.load(f)

            return agents
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

        # Debug logging
        logging.info(
            f"REGISTER: Registering agent '{agent_card.name}' with URL key: '{url_key}'"
        )

        # Add registration metadata
        agent_data = agent_card.model_dump()
        agent_data["_registered_at"] = datetime.now(timezone.utc).isoformat()

        agents[url_key] = agent_data
        self._save_agents(agents)

        logging.info(f"REGISTER: Successfully stored agent at URL key: '{url_key}'")

        return True

    def deregister_agent(self, agent_url: str) -> bool:
        """Deregister an agent by URL. Returns True if found and removed."""
        agents = self._load_agents()

        # Debug logging
        logging.info(f"DEREGISTER: Looking for agent with URL: '{agent_url}'")
        logging.info(f"DEREGISTER: Available URLs in storage: {list(agents.keys())}")

        if agent_url in agents:
            agent_name = agents[agent_url].get("name", "unknown")
            del agents[agent_url]
            self._save_agents(agents)
            logging.info(
                f"DEREGISTER: Successfully removed agent '{agent_name}' at '{agent_url}'"
            )

            return True

        logging.warning(f"DEREGISTER: Agent URL '{agent_url}' not found in storage")

        return False

    def get_registered_agents(self) -> List[AgentCard]:
        """Get all registered agents as AgentCard objects."""
        agents = self._load_agents()
        agent_cards = []
        parse_errors = 0

        for agent_data in agents.values():
            # Remove metadata before creating AgentCard
            clean_data = {k: v for k, v in agent_data.items() if not k.startswith("_")}

            try:
                # Convert capabilities from dict to A2ACapability objects
                if "capabilities" in clean_data and isinstance(
                    clean_data["capabilities"], dict
                ):
                    converted_capabilities = {}
                    for cap_name, cap_data in clean_data["capabilities"].items():
                        if isinstance(cap_data, dict):
                            # Convert dict to A2ACapability
                            converted_capabilities[cap_name] = A2ACapability(**cap_data)
                        else:
                            # Skip invalid capability data
                            logging.warning(
                                f"Skipping invalid capability {cap_name}: {cap_data}"
                            )
                    clean_data["capabilities"] = converted_capabilities

                # Convert authentication from dict to A2AAuthentication object
                auth_data = clean_data.get("authentication")
                if auth_data and isinstance(auth_data, dict):
                    clean_data["authentication"] = A2AAuthentication(**auth_data)

                # Convert endpoints from dict to A2AEndpoint objects
                if "endpoints" in clean_data and isinstance(clean_data["endpoints"], dict):
                    converted_endpoints = {}
                    for ep_name, ep_data in clean_data["endpoints"].items():
                        if isinstance(ep_data, dict):
                            converted_endpoints[ep_name] = A2AEndpoint(**ep_data)
                    clean_data["endpoints"] = converted_endpoints

                agent_cards.append(AgentCard(**clean_data))
            except Exception as e:
                logging.warning(f"Failed to parse stored agent: {e}")
                parse_errors += 1

        return agent_cards

    def get_uptime(self) -> float:
        """Get server uptime in seconds."""
        uptime = time.time() - self.start_time

        return uptime


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

# Initialize storage with absolute path
data_dir = Path.cwd() / REGISTRY_CONFIG["data_dir"]
storage = RegistryStorage(str(data_dir))

# Setup logging
logging.basicConfig(
    level=getattr(logging, REGISTRY_CONFIG["log_level"].upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# =============================================================================
# API Endpoints
# =============================================================================


@app.post("/register", status_code=201)
async def register_agent(agent_card: AgentCard):
    """
    Register an agent with the registry.

    Accepts a standard A2A AgentCard and stores it for discovery.
    """

    logging.info(f"REGISTER: Agent registration request received for agent '{agent_card.name}'")

    try:
        # Check if we're at capacity
        current_agents = len(storage.get_registered_agents())
        if current_agents >= REGISTRY_CONFIG["max_agents"]:
            max_agents = REGISTRY_CONFIG["max_agents"]

            logging.warning("REGISTER: Agent registration rejected - registry at capacity")

            raise HTTPException(
                status_code=429, detail=f"Registry at capacity ({max_agents} agents)"
            )

        success = storage.register_agent(agent_card)
        if success:
            response_data = {
                "message": "Agent registered successfully",
                "agent_url": agent_card.url,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }

            return response_data
        else:

            raise HTTPException(status_code=500, detail="Failed to register agent")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise


@app.post("/deregister")
async def deregister_agent(request: dict):
    """
    Deregister an agent from the registry.

    Accepts a JSON body with the agent URL to deregister.
    Body format: {"agent_url": "http://localhost:8080/agent-name"}
    """
    try:
        agent_url = request.get("agent_url")
        if not agent_url:
            raise HTTPException(status_code=400, detail="agent_url is required in request body")

        success = storage.deregister_agent(agent_url)
        if success:
            response_data = {
                "message": "Agent deregistered successfully",
                "agent_url": agent_url,
                "deregistered_at": datetime.now(timezone.utc).isoformat(),
            }
            return response_data
        else:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_url}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deregister agent: {str(e)}")


@app.get("/discover", response_model=DiscoveryResponse)
async def discover_agents(
    capabilities: Optional[str] = Query(None, description="Comma-separated capabilities filter"),
    tags: Optional[str] = Query(None, description="Comma-separated tags filter"),
    provider: Optional[str] = Query(None, description="Provider organization filter"),
):
    """
    Discover agents based on query parameters.

    Returns both hardcoded test agents and registered agents.
    Supports filtering by capabilities, tags, and provider organization.
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

        # Filter by capabilities (match against capability names)
        if capabilities:
            capability_list = [c.strip().lower() for c in capabilities.split(",")]
            filtered_agents = [
                agent
                for agent in filtered_agents
                if any(
                    capability in agent.capabilities.keys()
                    or any(capability in cap.name.lower() for cap in agent.capabilities.values())
                    for capability in capability_list
                )
            ]

        # Filter by tags (match against metadata.tags)
        if tags:
            tag_list = [t.strip().lower() for t in tags.split(",")]
            filtered_agents = [
                agent
                for agent in filtered_agents
                if agent.metadata.get("tags")
                and any(
                    tag in [t.lower() for t in agent.metadata.get("tags", [])] for tag in tag_list
                )
            ]

        # Filter by provider organization (match against metadata.organization)
        if provider:
            provider_filter = provider.strip().lower()
            filtered_agents = [
                agent
                for agent in filtered_agents
                if (
                    agent.metadata.get("organization")
                    and provider_filter in agent.metadata.get("organization", "").lower()
                )
            ]

        # Log discovery query completion

        response_data = DiscoveryResponse(
            agents=filtered_agents,
            total=len(filtered_agents),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        return response_data

    except Exception:
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

        response_data = HealthResponse(
            status="healthy",
            version="1.0.0",
            registered_agents=registered_count,
            uptime_seconds=uptime,
        )

        return response_data

    except Exception:
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
    print()
    print("Available endpoints:")
    print("  POST   /register          - Register an agent")
    print("  POST   /deregister        - Deregister an agent")
    print("  GET    /discover          - Discover agents")
    print("  GET    /health            - Health check")
    print()
    print("Example usage:")
    print("  curl http://localhost:9090/health")
    print("  curl http://localhost:9090/discover?capabilities=billing")
    print()

    # Run the server (auto-reload disabled to avoid import string issues)
    uvicorn.run(
        app,
        host=REGISTRY_CONFIG["host"],
        port=REGISTRY_CONFIG["port"],
        log_level=REGISTRY_CONFIG["log_level"],
        access_log=True,
    )


if __name__ == "__main__":
    main()
