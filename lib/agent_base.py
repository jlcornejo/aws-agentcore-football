"""Base agent factory for AI soccer position agents.

Pipeline per tick:
  1. state.py summarizes game state
  2. tactics.py computes tactical analysis (shot lanes, pass options, open space)
  3. LLM decides based on state + tactics
  4. parsing.py validates JSON output
  5. overrides.py corrects critical mistakes
  6. fallback.py catches failures
"""

import json
from typing import Callable
from strands import Agent
from strands.models import BedrockModel

from parsing import parse_commands
from state import summarize_state
from tactics import tactics_report
from overrides import apply_overrides
from fallback import FallbackConfig, build_last_resort
from pattern_tracker import PatternTracker


def create_agent(system_prompt: str, model_id: str = "us.amazon.nova-micro-v1:0") -> Agent:
    """Create a Strands Agent with the given system prompt."""
    model = BedrockModel(model_id=model_id, max_tokens=200, temperature=0.2)
    return Agent(model=model, system_prompt=system_prompt)


def create_invoke_handler(
    app,
    agent: Agent,
    my_player_id: int,
    position_label: str,
    fallback_fn: Callable[[dict, int, int], list[dict]],
    fallback_cfg: FallbackConfig,
):
    """Create and register the @app.entrypoint invoke handler.

    Pipeline: state summary + tactics → LLM → parse → overrides → output
    Four degradation layers: LLM → parse-fallback → error-fallback → last-resort
    """
    log = app.logger
    last_resort = build_last_resort(fallback_cfg, my_player_id)
    tracker = PatternTracker()  # In-process memory — survives across ticks

    @app.entrypoint
    async def invoke(payload, context):
        try:
            prompt = payload.get("prompt", "{}")
            prompt_data = json.loads(prompt) if isinstance(prompt, str) else prompt

            game_state = prompt_data.get("gameState", {})
            team_id = prompt_data.get("teamId", 0)

            my_players = prompt_data.get("myPlayers", [my_player_id])
            effective_pid = my_players[0] if my_players else my_player_id

            # Step 1: Summarize state
            state_summary = summarize_state(
                game_state, team_id, effective_pid, position_label
            )

            # Step 2: Compute tactics and append to prompt
            tactics = tactics_report(game_state, team_id, effective_pid, position_label)

            # Step 3: Pattern tracking (in-process memory)
            tracker.update(game_state, team_id)
            scouting = tracker.report(game_state, team_id, position_label)

            full_prompt = state_summary + tactics + scouting

            log.info(f"{position_label} agent invoked for team {team_id}, player {effective_pid}")

            # Step 3: LLM decides
            response = agent(full_prompt)
            response_text = str(response)

            # Step 4: Parse JSON
            commands = parse_commands(response_text, team_id, effective_pid)

            if commands:
                # Step 5: Apply overrides
                commands, override_tag = apply_overrides(
                    commands, game_state, team_id, effective_pid, position_label
                )
                if override_tag:
                    log.info(f"Override [{override_tag}]: {[c.get('commandType') for c in commands]}")
                else:
                    log.info(f"LLM: {[c.get('commandType') for c in commands]}")
                yield json.dumps(commands)
            else:
                log.warn(f"LLM parse failed, using fallback. Response: {response_text[:200]}")
                commands = fallback_fn(game_state, team_id, effective_pid)
                # Apply overrides even to fallback commands
                commands, override_tag = apply_overrides(
                    commands, game_state, team_id, effective_pid, position_label
                )
                log.info(f"Fallback{' ['+override_tag+']' if override_tag else ''}: {[c.get('commandType') for c in commands]}")
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
                cmd["teamId"] = 0
                yield json.dumps([cmd])

    return invoke
