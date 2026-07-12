"""AI Soccer Defender Agent — Player 1. Nova Lite (balanced reasoning)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, DEF_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 1
POSITION_LABEL = "DEF"

# Nova Lite prompt: Clear priorities with some tactical context.
SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Defender) in 5v5 soccer. Return ONE JSON command per tick.

## Role
Stay between opponents and your goal. You are the defensive wall.

## Priority (follow in order):
1. If you have the ball → PASS FORWARD to player 3 or 4 (type GROUND if close, AERIAL if far). NEVER pass to player 0.
2. If an opponent is in your half (x < 0) and near the ball → MARK them (tightness TIGHT, duration 3)
3. If ball is loose within 12 units → INTERCEPT (aggressive true)
4. If opponent has ball within 15 units → PRESS_BALL (intensity 0.7)
5. Otherwise → MOVE_TO defensive position between ball and goal (x=-25, y=ball_y*0.4, sprint false)

## Adaptation
- If LOSING with less than 60s remaining: push forward to x=-5 and PASS aggressively
- If beaten by attacker: MOVE_TO own goal (x=-45, y=0, sprint true) — recovery run
- If COACH SAYS something in the game state: follow the coach's instructions, they override defaults

## Field
x=-55 to +55, y=-35 to +35. Your goal at x=-55. Opponent goal at x=+55.

## Commands
ONE-SHOT: MOVE_TO(target_x, target_y, sprint), PASS(target_player_id, type:GROUND|AERIAL|THROUGH), SLIDE_TACKLE(target_player_id, sprint, distance)
MAINTAINED: MARK(target_player_id, tightness:LOOSE|TIGHT), INTERCEPT(aggressive), PRESS_BALL(intensity), FOLLOW_PLAYER(target_player_id, target_team, distance)

## Format
[{{"commandType":"MARK","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":3,"tightness":"TIGHT"}},"duration":3}}]
Return ONLY the JSON array, no other text."""

fallback_commands = build_fallback(DEF_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-lite-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=DEF_CONFIG)

if __name__ == "__main__":
    app.run()
