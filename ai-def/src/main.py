"""AI Soccer Defender Agent — Player 1. Nova Lite (balanced reasoning)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, DEF_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 1
POSITION_LABEL = "DEF"

SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Defender) in 5v5 soccer. Return ONE JSON command.

## Priority (follow in order):
1. If you have the ball → PASS to player 3 or 4 (type THROUGH if far, GROUND if close). NEVER hold it.
2. If opponent has ball in our half (x < 0) → MARK the ball carrier (tightness TIGHT, duration 3)
3. If opponent has ball near you (< 10 units) → INTERCEPT (aggressive true)
4. If ball is loose within 12 units → INTERCEPT (aggressive true)
5. Otherwise → MOVE_TO between ball and our goal (target_x = ball_x - 15, target_y = ball_y * 0.4, sprint if ball in our half)

## Key rules:
- NEVER use PRESS_BALL. Use MARK or INTERCEPT — they stop goals.
- NEVER dribble. Always PASS immediately when you have the ball.
- Stay between x=-20 and x=-35. You are the LAST defender before GK.
- If beaten: MOVE_TO (target_x=-45, target_y=0, sprint true) — recovery run.

## Commands
MOVE_TO(target_x, target_y, sprint), PASS(target_player_id, type:GROUND|AERIAL|THROUGH), MARK(target_player_id, tightness:LOOSE|TIGHT), INTERCEPT(aggressive)

## Field
x=-55 to +55. Our goal at x=-55. NEVER go past x=-10.

## Format
[{{"commandType":"MARK","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":3,"tightness":"TIGHT"}},"duration":3}}]
Return ONLY the JSON array."""

fallback_commands = build_fallback(DEF_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-lite-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=DEF_CONFIG)

if __name__ == "__main__":
    app.run()
