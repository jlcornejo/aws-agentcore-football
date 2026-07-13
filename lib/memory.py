"""
AgentCore Memory integration for AI soccer agents.

Provides short-term memory so agents can recall previous ticks' patterns:
- What the opponent was doing (tracking runs, pressing patterns)
- Coaching instructions received via teamChat
- Shots/passes attempted and their outcomes

Memory is optional and controlled by environment variables:
- MEMORY_ENABLED=true/false (default: false)
- MEMORY_ID=<memory-id> (from AgentCore)
- MEMORY_ACTOR_ID=<actor-id> (unique per team, shared across agents)
- MEMORY_BATCH_SIZE=5 (buffer messages before sending)

Design decisions for football:
- Each agent gets its own session_id (position_label + match context)
- All agents share the same actor_id (team-level memory)
- Batch size is tuned to reduce API calls within the 5s timeout
- Memory is SHORT-TERM only (no long-term strategies) to avoid latency
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

MEMORY_ENABLED = os.environ.get("MEMORY_ENABLED", "false").lower() == "true"
MEMORY_ID = os.environ.get("MEMORY_ID")
MEMORY_ACTOR_ID = os.environ.get("MEMORY_ACTOR_ID", "football-team")
MEMORY_BATCH_SIZE = int(os.environ.get("MEMORY_BATCH_SIZE", "5"))
MEMORY_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# Session manager factory
# ---------------------------------------------------------------------------

def create_memory_session_manager(position_label: str, session_id: Optional[str] = None):
    """Create an AgentCoreMemorySessionManager for a football agent.

    Returns None if memory is disabled or misconfigured.
    The caller should pass this to Agent(session_manager=...) if not None.

    Args:
        position_label: GK, DEF, MID, FWD1, FWD2
        session_id: Optional override. Defaults to position_label-based ID.

    Returns:
        AgentCoreMemorySessionManager instance, or None.
    """
    if not MEMORY_ENABLED:
        logger.info(f"{position_label}: Memory DISABLED (set MEMORY_ENABLED=true to enable)")
        return None

    if not MEMORY_ID:
        logger.warning(f"{position_label}: MEMORY_ENABLED=true but MEMORY_ID not set. Skipping memory.")
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
    except ImportError as e:
        logger.warning(f"{position_label}: bedrock_agentcore memory module not available: {e}")
        return None

    # Session ID: unique per agent position within a match
    effective_session_id = session_id or f"match-{position_label.lower()}"

    config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=effective_session_id,
        actor_id=MEMORY_ACTOR_ID,
        batch_size=MEMORY_BATCH_SIZE,
    )

    try:
        session_mgr = AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=MEMORY_REGION,
        )
        logger.info(
            f"{position_label}: Memory ENABLED "
            f"(id={MEMORY_ID}, session={effective_session_id}, actor={MEMORY_ACTOR_ID})"
        )
        return session_mgr
    except Exception as e:
        logger.error(f"{position_label}: Failed to create memory session manager: {e}")
        return None
