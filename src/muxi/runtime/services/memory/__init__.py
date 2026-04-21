# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Package - Conversation and Knowledge Storage
# Description:  Memory system implementations for the Muxi framework
# Role:         Provides short and long-term storage for agent interactions
# Usage:        Imported by components needing memory capabilities
# Author:       Muxi Framework Team
#
# The memory package provides various memory implementations for storing and
# retrieving information in the Muxi framework. This includes:
#
# 1. Working Memory (WorkingMemory)
#    - Stores recent conversation history
#    - Implements semantic search via vector embeddings
#    - Balances recency and relevance for context retrieval
#
# 2. Long-Term Memory (LongTermMemory)
#    - Persistent storage for important information
#    - Uses PostgreSQL with pgvector for scalable vector search
#    - Supports metadata filtering and collection organization
#
# 3. Context Memory
#    - Stores user-specific information and preferences
#    - Enables personalization of agent responses
#    - Structured storage with simple query interface
#
# 4. SQLite-Based Storage
#    - Local-first vector database implementation
#    - Uses SQLite with vector extension for similarity search
#    - Ideal for edge deployments and development environments
#
# 5. Base Abstractions
#    - Common interfaces for all memory implementations
#    - Standardized methods for adding and retrieving information
#    - Extensible design for custom memory implementations
#
# Memory systems are a core component of the framework, enabling agents to:
# - Maintain conversation context across multiple turns
# - Remember important information about users and topics
# - Retrieve relevant information based on semantic similarity
# - Provide personalized and contextually appropriate responses
#
# Embedding generation is centralized in the ``embedding`` submodule, which
# routes all embedding calls through OneLLM's provider-prefixed slug system
# (e.g. ``local/nomic-ai/nomic-embed-text-v1.5``,
# ``openai/text-embedding-3-small``). Memory tiers accept a string slug via
# the ``embedding_model`` kwarg and probe dimensions lazily on first use.
# =============================================================================

from .base import BaseMemory
from .long_term import LongTermMemory
from .memobase import Memobase
from .sqlite import SQLiteMemory
from .working import WorkingMemory

__all__ = [
    "BaseMemory",
    "WorkingMemory",
    "LongTermMemory",
    "Memobase",
    "SQLiteMemory",
]
