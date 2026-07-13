"""Invoke handler for Gateway-enabled agents.

Similar to agent_base.create_invoke_handler, but wraps the agent call
inside the MCPClient context manager so Gateway tools are available
during invocation. Supports dynamic prompts and guardrails.
"""

import json
from typing import Callable, Optional

from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient

from parsing import parse_commands
from state import summarize_state, get_goal_positions
from fallback import FallbackConfig, build_last_resort
from prompt_manager import PromptCache, get_prompt_id_for_position


def _fix_own_goal_move(commands: list[dict], team_id: int, position_label: str, log) -> list[dict]:
    """Reject MOVE_TO commands that send attacking players toward their own goal."""
    my_goal_x, opp_goal_x = get_goal_positions(team_id)

    for cmd in commands:
        if cmd.get("commandType") != "MOVE_TO":
            continue
        params = cmd.get("parameters", {})
        target_x = params.get("target_x")
        if target_x is None:
            continue

        if position_label in ("FWD1", "FWD2", "MID"):
            if abs(target_x - my_goal_x) < 10:
                corrected_x = opp_goal_x * 0.6
                log.warn(f"Blocked own-goal MOVE_TO x={target_x} for {position_label}, "
                         f"corrected to x={corrected_x}")
                params["target_x"] = corrected_x

        elif position_label == "DEF":
            if abs(target_x - opp_goal_x) < 5:
                corrected_x = 0.0
                log.warn(f"Blocked over-run MOVE_TO x={target_x} for DEF, "
                         f"corrected to x={corrected_x}")
                params["target_x"] = corrected_x

    return commands


def create_gateway_invoke_handler(
    app,
    agent: Agent,
    mcp_client: MCPClient,
    my_player_id: int,
    position_label: str,
    fallback_fn: Callable[[dict, int, int], list[dict]],
    fallback_cfg: FallbackConfig,
):
    """Register the @app.entrypoint handler with Gateway MCP context.

    Supports:
      - Dynamic prompt refresh from Bedrock Prompt Management
      - Guardrails intervention handling
      - Own-goal MOVE_TO correction
      - Three-layer fallback (LLM+tools → rule-based → last-resort)
    """
    log = app.logger
    last_resort = build_last_resort(fallback_cfg, my_player_id)

    # --- Dynamic prompt setup ---
    prompt_id = get_prompt_id_for_position(position_label)
    prompt_cache: Optional[PromptCache] = None
    if prompt_id:
        current_prompt = agent.system_prompt if hasattr(agent, 'system_prompt') else ""
        prompt_cache = PromptCache(prompt_id, fallback_prompt=current_prompt)
        log.info(f"{position_label}: Dynamic prompts ENABLED (id={prompt_id})")
    else:
        log.info(f"{position_label}: Using static prompt (no PROMPT_ID env var)")

    # --- Gateway info ---
    import os
    gateway_url = os.environ.get("GATEWAY_URL", "NOT_SET")
    log.info(f"{position_label}: Gateway ENABLED (url={gateway_url[:60]}...)")

    @app.entrypoint
    async def invoke(payload, context):
        try:
            # Refresh prompt if dynamic prompts are enabled
            if prompt_cache:
                new_prompt = prompt_cache.get_prompt()
                if hasattr(agent, 'system_prompt'):
                    agent.system_prompt = new_prompt

            prompt = payload.get("prompt", "{}")
            prompt_data = json.loads(prompt) if isinstance(prompt, str) else prompt

            game_state = prompt_data.get("gameState", {})
            team_id = prompt_data.get("teamId", 0)

            # Honor myPlayers from payload if present, otherwise use configured player ID
            my_players = prompt_data.get("myPlayers", [my_player_id])
            effective_pid = my_players[0] if my_players else my_player_id

            state_summary = summarize_state(
                game_state, team_id, effective_pid, position_label
            )
            log.info(f"{position_label} gateway agent invoked for team {team_id}, "
                     f"controlling player {effective_pid}")

            # Use MCP client context so Gateway tools are available
            with mcp_client:
                response = agent(state_summary)
            response_text = str(response)

            # If guardrail intervened, skip parsing and go to fallback
            if hasattr(response, 'stop_reason') and response.stop_reason == "guardrail_intervened":
                log.warn(f"{position_label}: Guardrail intervened, using fallback")
                commands = fallback_fn(game_state, team_id, effective_pid)
                yield json.dumps(commands)
                return

            commands = parse_commands(response_text, team_id, effective_pid)

            # --- Sanity check: reject MOVE_TO toward own goal ---
            if commands:
                commands = _fix_own_goal_move(commands, team_id, position_label, log)

            if commands:
                log.info(f"LLM+tools returned {len(commands)} commands: "
                         f"{[c.get('commandType') for c in commands]}")
                yield json.dumps(commands)
            else:
                log.warn(f"LLM parse failed, using fallback. Response: {response_text[:200]}")
                commands = fallback_fn(game_state, team_id, effective_pid)
                yield json.dumps(commands)

        except Exception as e:
            log.error(f"{position_label} gateway agent error: {e}")
            try:
                prompt_data = json.loads(payload.get("prompt", "{}"))
                team_id = prompt_data.get("teamId", 0)
                my_players = prompt_data.get("myPlayers", [my_player_id])
                effective_pid = my_players[0] if my_players else my_player_id
                commands = fallback_fn(
                    prompt_data.get("gameState", {}), team_id, effective_pid,
                )
                yield json.dumps(commands)
            except Exception:
                cmd = dict(last_resort)
                cmd["teamId"] = 0
                yield json.dumps([cmd])

    return invoke
