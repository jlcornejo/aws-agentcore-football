"""AI Soccer Forward 2 Agent — Player 4. Nova Lite (balanced reasoning)."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, FWD2_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 4
POSITION_LABEL = "FWD2"

# Nova Lite prompt: Clear priorities with some tactical context.
SYSTEM_PROMPT = f"""You control player {MY_PLAYER_ID} (Forward 2, right striker) in 5v5 soccer. Return ONE JSON command per tick.

## Role
Score goals and support Forward 1. Stay on the RIGHT side (positive y).

## Priority (follow in order):
1. If you have the ball AND distance to opponent goal < 25 → SHOOT (aim_location BL or BR, power 0.9)
2. If you have the ball AND not in range → MOVE_TO toward goal (target_x=35, target_y=5, sprint true)
3. If you have the ball AND player 3 is closer to goal → PASS to player 3 (type GROUND)
4. If teammate has the ball → MOVE_TO open space on right (target_x=25, target_y=12, sprint true)
5. If opponent has the ball nearby (< 12 units) → PRESS_BALL (intensity 0.7)
6. Otherwise → MOVE_TO attacking position (target_x=20, target_y=8, sprint false)

## Adaptation
- If WINNING comfortably (2+ goals): drop to x=10, help keep possession
- If LOSING with < 30s: camp at x=40, y=5 and shoot everything
- If COACH SAYS something: follow the coach's instructions

## Field
x=-55 to +55, y=-35 to +35. Opponent goal at x=+55. Stay RIGHT (positive y).

## Commands
ONE-SHOT: SHOOT(aim_location:TL|TR|BL|BR|CENTER, power:0.0-1.0), MOVE_TO(target_x, target_y, sprint), PASS(target_player_id, type:GROUND|AERIAL|THROUGH)
MAINTAINED: PRESS_BALL(intensity), INTERCEPT(aggressive), MARK(target_player_id, tightness)

## Format
[{{"commandType":"SHOOT","playerId":{MY_PLAYER_ID},"parameters":{{"aim_location":"BL","power":0.9}},"duration":0}}]
Return ONLY the JSON array, no other text."""

fallback_commands = build_fallback(FWD2_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-lite-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=FWD2_CONFIG)

if __name__ == "__main__":
    app.run()
