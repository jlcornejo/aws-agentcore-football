"""Memory-aware agent factory — extends agent_base with AgentCore Memory.

Use this INSTEAD of create_agent when you have AgentCore Memory deployed.
Falls back to a normal agent if MEMORY_ID env var is not set.

Required env vars for memory mode:
  MEMORY_ID  — AgentCore Memory resource ID (from agentcore add memory)
  AWS_DEFAULT_REGION — region where memory is deployed

Optional:
  TEAM_ID   — used as session prefix (default: "stars")
  MATCH_TAG — isolate sessions per match (prevents cross-match pollution)

Usage in ai-*/src/main.py:
    from memory_agent_base import create_memory_agent
    agent = create_memory_agent(SYSTEM_PROMPT, MY_PLAYER_ID, POSITION_LABEL,
                                model_id="us.amazon.nova-pro-v1:0")
"""

import os
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel


def create_memory_agent(
    system_prompt: str,
    player_id: int,
    position_label: str,
    model_id: str = "us.amazon.nova-micro-v1:0",
    temperature: float = 0.2,
    max_tokens: int = 200,
    window_ticks: int = 5,
) -> Agent:
    """Create a Strands Agent with AgentCore Memory for cross-tick recall.

    If MEMORY_ID is not set, falls back to a normal agent (no memory).
    """
    memory_id = os.environ.get("MEMORY_ID")

    model = BedrockModel(model_id=model_id, temperature=temperature,
                         max_tokens=max_tokens)

    if not memory_id:
        # No memory configured — return normal agent
        return Agent(model=model, system_prompt=system_prompt,
                     callback_handler=None)

    # Import AgentCore Memory (only available when deployed)
    try:
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
        )
    except ImportError:
        # Not deployed to AgentCore — fall back to normal agent
        return Agent(model=model, system_prompt=system_prompt,
                     callback_handler=None)

    team_id = os.environ.get("TEAM_ID", "stars")
    match_tag = os.environ.get("MATCH_TAG", "")

    session_id = f"match-{team_id}-{position_label}"
    if match_tag:
        session_id = f"{session_id}-{match_tag}"

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=session_id,
            actor_id=f"{team_id}-{position_label}",
            batch_size=2,
        ),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        session_manager=session_manager,
        conversation_manager=SlidingWindowConversationManager(
            window_size=window_ticks * 2
        ),
        callback_handler=None,
    )
