"""Base agent factory for AI soccer position agents."""

import json
from typing import Callable, Optional
from strands import Agent
from strands.models import BedrockModel

from parsing import parse_commands
from state import summarize_state, get_goal_positions
from fallback import FallbackConfig, build_last_resort
from prompt_manager import PromptCache, get_prompt_id_for_position


def create_agent(system_prompt: str, model_id: str = "us.amazon.nova-micro-v1:0") -> Agent:
    """Create a Strands Agent with the given system prompt."""
    model = BedrockModel(model_id=model_id)
    return Agent(model=model, system_prompt=system_prompt)


def _fix_own_goal_move(commands: list[dict], team_id: int, position_label: str, log) -> list[dict]:
    """Reject MOVE_TO commands that send attacking players toward their own goal.

    The Strands multi-turn bug sometimes produces MOVE_TO x=-55 (own goal for HOME)
    or MOVE_TO x=+55 (own goal for AWAY). For FWD/MID positions this is never correct.
    We flip the x coordinate to the opponent's side.
    """
    my_goal_x, opp_goal_x = get_goal_positions(team_id)

    for cmd in commands:
        if cmd.get("commandType") != "MOVE_TO":
            continue
        params = cmd.get("parameters", {})
        target_x = params.get("target_x")
        if target_x is None:
            continue

        # For attacking players (FWD1, FWD2, MID): reject if running toward own goal
        if position_label in ("FWD1", "FWD2", "MID"):
            # Own goal is at my_goal_x. If target_x is within 10 units of own goal, it's wrong.
            if abs(target_x - my_goal_x) < 10:
                # Flip to opponent side — mirror the x coordinate
                corrected_x = opp_goal_x * 0.6  # ~33 for HOME, ~-33 for AWAY
                log.warn(f"Blocked own-goal MOVE_TO x={target_x} for {position_label}, "
                         f"corrected to x={corrected_x}")
                params["target_x"] = corrected_x

        # For DEF: reject if running past opponent goal (into the stands)
        elif position_label == "DEF":
            if abs(target_x - opp_goal_x) < 5:
                corrected_x = 0.0  # midfield
                log.warn(f"Blocked over-run MOVE_TO x={target_x} for DEF, "
                         f"corrected to x={corrected_x}")
                params["target_x"] = corrected_x

    return commands


def create_invoke_handler(
    app,
    agent: Agent,
    my_player_id: int,
    position_label: str,
    fallback_fn: Callable[[dict, int, int], list[dict]],
    fallback_cfg: FallbackConfig,
):
    """Create and register the @app.entrypoint invoke handler.

    Three layers of error handling, from best to worst:
      1. LLM response → parse into commands
      2. fallback_fn(game_state, team_id, my_player_id) → rule-based commands
      3. last-resort command from fallback_cfg → single safe command

    Dynamic prompt:
      If PROMPT_ID_<POSITION> or PROMPT_ID env var is set, the agent's
      system_prompt is refreshed from Bedrock Prompt Management on a TTL basis.
      This allows updating tactics without redeploying.
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
            log.info(f"{position_label} agent invoked for team {team_id}, controlling player {effective_pid}")

            response = agent(state_summary)
            response_text = str(response)

            # Strands may produce multi-turn responses. The last turn often
            # hallucinates (e.g. MOVE_TO own goal). Try parsing the full
            # response first; if that yields a valid command whose MOVE_TO
            # target is clearly wrong (behind our own goal), fall through to
            # the first parseable chunk instead.
            commands = parse_commands(response_text, team_id, effective_pid)

            # --- Sanity check: reject MOVE_TO toward own goal ---
            if commands:
                commands = _fix_own_goal_move(commands, team_id, position_label, log)

            if commands:
                log.info(f"LLM returned {len(commands)} commands: "
                         f"{[c.get('commandType') for c in commands]}")
                yield json.dumps(commands)
            else:
                log.warn(f"LLM parse failed, using fallback. Response: {response_text[:200]}")
                commands = fallback_fn(game_state, team_id, effective_pid)
                log.info(f"Fallback returned {len(commands)} commands")
                yield json.dumps(commands)

        except Exception as e:
            log.error(f"{position_label} agent error: {e}")
            try:
                prompt_data = json.loads(payload.get("prompt", "{}"))
                team_id = prompt_data.get("teamId", 0)
                my_players = prompt_data.get("myPlayers", [my_player_id])
                effective_pid = my_players[0] if my_players else my_player_id
                commands = fallback_fn(
                    prompt_data.get("gameState", {}),
                    team_id,
                    effective_pid,
                )
                yield json.dumps(commands)
            except Exception:
                cmd = dict(last_resort)
                cmd["teamId"] = 0  # best guess when payload parsing also failed
                yield json.dumps([cmd])

    return invoke
