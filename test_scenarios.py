"""Test de escenarios tácticos — valida decisiones contra Bedrock.

Envía game states específicos al LLM y verifica que cada agente
toma la decisión correcta. No depende del simulador.

Usage:
    python test_scenarios.py          # Solo overrides (sin AWS)
    python test_scenarios.py --llm    # Con LLM real (requiere AWS)
"""

import sys
import os
import json
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from test_helpers import mock_agentcore
mock_agentcore()

from state import summarize_state
from parsing import parse_commands
from tactics import tactics_report
from overrides import apply_overrides
from fallback import (build_fallback, GK_CONFIG, DEF_CONFIG,
                      MID_CONFIG, FWD1_CONFIG, FWD2_CONFIG)

# === BASE PLAYERS (reused across scenarios) ===
def _home_players(positions):
    """Create home players at given positions. positions = [(x,y), ...]"""
    return [{"agentId": f"agentId_{i}", "teamCode": "home",
             "position": {"x": p[0], "y": p[1]}, "velocity": {"x": 0, "y": 0},
             "stamina": 0.8, "speed": 0, "isSprinting": False,
             "orientation": 0, "currentAction": 0, "lastAction": ""}
            for i, p in enumerate(positions)]

def _away_players(positions):
    return [{"agentId": f"agentId_{i}", "teamCode": "away",
             "position": {"x": p[0], "y": p[1]}, "velocity": {"x": 0, "y": 0},
             "stamina": 0.8, "speed": 0, "isSprinting": False,
             "orientation": 0, "currentAction": 0, "lastAction": ""}
            for i, p in enumerate(positions)]

def _make_state(home_pos, away_pos, ball_x, ball_y, possessor_id,
                score_home=0, score_away=0, game_time=120):
    return {
        "tick": int(game_time / 2), "gameTime": game_time,
        "playMode": "OPEN_PLAY", "modeTeamId": None,
        "score": {"home": score_home, "away": score_away},
        "ball": {
            "position": {"x": ball_x, "y": ball_y, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "isFree": possessor_id is None,
            "possessionAgentId": f"agentId_{possessor_id}" if possessor_id is not None else None,
            "rotation": {}, "angularVelocity": {},
        },
        "players": _home_players(home_pos) + _away_players(away_pos),
        "teamChat": [],
    }

# === 10 SCENARIOS ===
SCENARIOS = [
    {
        "name": "1. FWD1 shoots — in range, clear lane",
        "agent_id": 3, "position": "FWD1", "model": "us.amazon.nova-micro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,-5), (10,3), (35,-2), (25,10)],
            away_pos=[(50,0), (30,8), (20,-10), (0,-5), (0,5)],
            ball_x=35, ball_y=-2, possessor_id=3),
        "expect": ["SHOOT"],
        "reason": "FWD1 has ball 20m from goal, lane clear → must shoot",
    },
    {
        "name": "2. MID passes forward to FWD",
        "agent_id": 2, "position": "MID", "model": "us.amazon.nova-pro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,-5), (5,0), (30,-8), (28,8)],
            away_pos=[(50,0), (25,5), (15,0), (-5,-10), (-5,10)],
            ball_x=5, ball_y=0, possessor_id=2),
        "expect": ["PASS", "SHOOT"],
        "reason": "MID has ball, FWDs are open ahead → pass or advance",
    },
    {
        "name": "3. GK distributes quickly",
        "agent_id": 0, "position": "GK", "model": "us.amazon.nova-micro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,5), (0,0), (15,-8), (15,8)],
            away_pos=[(50,0), (20,0), (10,5), (-10,-10), (-10,10)],
            ball_x=-50, ball_y=0, possessor_id=0),
        "expect": ["GK_DISTRIBUTE"],
        "reason": "GK has ball, no pressure → distribute to outfield",
    },
    {
        "name": "4. DEF under pressure — aerial clear",
        "agent_id": 1, "position": "DEF", "model": "us.amazon.nova-lite-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-25,0), (5,5), (20,-8), (20,8)],
            away_pos=[(50,0), (-20,3), (-22,-3), (-10,10), (-10,-10)],
            ball_x=-25, ball_y=0, possessor_id=1),
        "expect": ["PASS", "SHOOT"],
        "reason": "DEF has ball, 2 opponents within 5m → pass or clear",
    },
    {
        "name": "5. Counter-attack — high press",
        "agent_id": 2, "position": "MID", "model": "us.amazon.nova-pro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-15,0), (-10,3), (25,-8), (25,8)],
            away_pos=[(50,0), (-8,5), (-12,-5), (-5,0), (-18,10)],
            ball_x=-10, ball_y=3, possessor_id=2),
        "expect": ["PASS"],
        "reason": "MID has ball, 3+ opponents in our half → through ball to FWD",
    },
]

SCENARIOS += [
    {
        "name": "6. FWD2 moves to space — teammate has ball",
        "agent_id": 4, "position": "FWD2", "model": "us.amazon.nova-lite-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,0), (10,0), (15,-5), (5,3)],
            away_pos=[(50,0), (25,8), (15,-5), (0,10), (0,-10)],
            ball_x=10, ball_y=0, possessor_id=2),
        "expect": ["MOVE_TO"],
        "reason": "MID has ball, FWD2 is behind → move to attacking space",
    },
    {
        "name": "7. DEF marks dangerous opponent",
        "agent_id": 1, "position": "DEF", "model": "us.amazon.nova-lite-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,0), (0,0), (15,-8), (15,8)],
            away_pos=[(50,0), (-15,3), (5,0), (-25,-5), (10,10)],
            ball_x=-15, ball_y=3, possessor_id=None),
        "expect": ["MARK", "PRESS_BALL", "INTERCEPT"],
        "reason": "Opponent at (-15,3) near our goal with ball → mark or press",
    },
    {
        "name": "8. Last minute losing — MID all-out attack",
        "agent_id": 2, "position": "MID", "model": "us.amazon.nova-pro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-10,0), (20,0), (30,-5), (30,5)],
            away_pos=[(50,0), (25,8), (15,0), (5,-10), (5,10)],
            ball_x=20, ball_y=0, possessor_id=2,
            score_home=0, score_away=1, game_time=280),
        "expect": ["SHOOT", "PASS", "MOVE_TO"],
        "reason": "Losing 0-1, 20s left, has ball at x=20 → shoot or advance aggressively",
    },
    {
        "name": "9. Winning comfortably — MID keeps possession",
        "agent_id": 2, "position": "MID", "model": "us.amazon.nova-pro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,-5), (5,0), (20,-8), (20,8)],
            away_pos=[(50,0), (25,5), (15,0), (-5,-10), (-5,10)],
            ball_x=5, ball_y=0, possessor_id=2,
            score_home=2, score_away=0, game_time=240),
        "expect": ["PASS", "MOVE_TO"],
        "reason": "Winning 2-0, 60s left → safe pass or hold position",
    },
    {
        "name": "10. GK smothers loose ball in box",
        "agent_id": 0, "position": "GK", "model": "us.amazon.nova-micro-v1:0",
        "state": _make_state(
            home_pos=[(-50,0), (-20,5), (0,0), (15,-8), (15,8)],
            away_pos=[(50,0), (20,0), (-40,5), (-35,-5), (10,10)],
            ball_x=-45, ball_y=3, possessor_id=None),
        "expect": ["INTERCEPT", "MOVE_TO"],
        "reason": "Ball loose at (-45,3), 5m from GK in box → intercept",
    },
]

# === TEST RUNNER ===
def run_scenario_overrides(scenario):
    """Test with overrides only (no LLM call)."""
    state = scenario["state"]
    pid = scenario["agent_id"]
    pos = scenario["position"]
    tid = 0

    # Use fallback to generate a command, then apply overrides
    configs = {0: GK_CONFIG, 1: DEF_CONFIG, 2: MID_CONFIG, 3: FWD1_CONFIG, 4: FWD2_CONFIG}
    fb = build_fallback(configs[pid])
    commands = fb(state, tid, pid)
    commands, tag = apply_overrides(commands, state, tid, pid, pos)
    return commands, tag


def run_scenario_llm(scenario):
    """Test with real LLM call + overrides."""
    from strands import Agent
    from strands.models import BedrockModel

    state = scenario["state"]
    pid = scenario["agent_id"]
    pos = scenario["position"]
    model_id = scenario["model"]
    tid = 0

    # Load the agent's prompt
    agent_dirs = {0: "ai-gk", 1: "ai-def", 2: "ai-mid", 3: "ai-fwd1", 4: "ai-fwd2"}
    spec = importlib.util.spec_from_file_location(
        f"agent_{pid}",
        os.path.join(os.path.dirname(__file__), agent_dirs[pid], "src", "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    model = BedrockModel(model_id=model_id, max_tokens=200, temperature=0.2)
    agent = Agent(model=model, system_prompt=mod.SYSTEM_PROMPT)

    # Build prompt with tactics
    summary = summarize_state(state, tid, pid, pos)
    tactics = tactics_report(state, tid, pid, pos)
    full_prompt = summary + tactics

    # Call LLM
    response = agent(full_prompt)
    response_text = str(response)

    # Parse + overrides
    commands = parse_commands(response_text, tid, pid)
    if commands:
        commands, tag = apply_overrides(commands, state, tid, pid, pos)
    else:
        commands = [{"commandType": "PARSE_FAILED", "raw": response_text[:100]}]
        tag = "parse-failed"

    return commands, tag, response_text


def main():
    use_llm = "--llm" in sys.argv
    mode = "LLM + Overrides" if use_llm else "Overrides Only (fallback → override)"

    print(f"\n{'═' * 60}")
    print(f"  ⚽ TEST DE ESCENARIOS TÁCTICOS")
    print(f"  Modo: {mode}")
    print(f"{'═' * 60}\n")

    passed, failed = 0, 0

    for s in SCENARIOS:
        print(f"📌 {s['name']}")
        print(f"   Razón: {s['reason']}")

        if use_llm:
            commands, tag, raw = run_scenario_llm(s)
            cmd_type = commands[0].get("commandType", "?") if commands else "?"
            params = commands[0].get("parameters", {}) if commands else {}
            print(f"   LLM raw: {raw[:80]}")
        else:
            commands, tag = run_scenario_overrides(s)
            cmd_type = commands[0].get("commandType", "?") if commands else "?"
            params = commands[0].get("parameters", {}) if commands else {}

        override_info = f" [override: {tag}]" if tag else ""
        ok = cmd_type in s["expect"]
        status = "✅ PASS" if ok else "❌ FAIL"

        if ok:
            passed += 1
        else:
            failed += 1

        print(f"   → {cmd_type} {params}{override_info}")
        print(f"   Expected: {s['expect']}")
        print(f"   {status}")
        print()

    print(f"{'═' * 60}")
    print(f"  Resultado: {passed} passed, {failed} failed de {len(SCENARIOS)}")
    if failed == 0:
        print(f"  🏆 ¡Todos los escenarios pasan!")
    else:
        print(f"  ⚠️  {failed} escenario(s) necesitan ajuste")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
