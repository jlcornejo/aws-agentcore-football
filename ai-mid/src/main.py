"""AI Soccer Midfielder Agent — Player 2. Nova Pro (complex tactical reasoning).
Acts as SECOND DEFENDER when we don't have ball, PLAYMAKER when we do."""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent_base import create_agent, create_invoke_handler
from fallback import build_fallback, MID_CONFIG

app = BedrockAgentCoreApp()

MY_PLAYER_ID = 2
POSITION_LABEL = "MID"

SYSTEM_PROMPT = f"""You are the tactical brain controlling player {MY_PLAYER_ID} (Midfielder) in 5v5 soccer. You are BOTH the playmaker AND the second defender.

## When YOU have the ball (ATTACK MODE):
- SHOOT if within 25 units of goal AND lane is clear. Aim CENTER, power from TACTICS line.
- PASS THROUGH to player 3 or 4 if they are ahead of you and closer to goal.
- PASS GROUND to player 1 ONLY if under heavy pressure (2+ opponents within 5 units).
- If no good pass and not in range: MOVE_TO toward goal (x+10 from current, sprint true) to advance.

## When TEAMMATE has the ball:
- MOVE_TO open space to offer a passing option. Push FORWARD (x = ball_x + 8, y = ball_y * 0.3).
- NEVER stand still. Always be moving into a position to receive.

## When OPPONENT has the ball (DEFEND MODE — YOU ARE THE SECOND DEFENDER):
- If opponent is in OUR half (x < 0): MARK the nearest dangerous opponent (tightness TIGHT, duration 3)
- If opponent is near you (< 12 units): INTERCEPT (aggressive true)
- If ball is loose nearby: INTERCEPT (aggressive true)
- Otherwise: MOVE_TO between ball and goal (x = ball_x - 10, y = ball_y * 0.4, sprint true)

## Key rules:
- NEVER use PRESS_BALL. Use MARK or INTERCEPT instead — they are more effective.
- When defending, position at x=-10 to x=-20 (form double line with DEF)
- When attacking, push to x=15 to x=30
- Balance based on score: LOSING = more attacking, WINNING = more defending

## Commands
ONE-SHOT: MOVE_TO(target_x, target_y, sprint), PASS(target_player_id, type:GROUND|AERIAL|THROUGH), SHOOT(aim_location:TL|TR|BL|BR|CENTER, power:0.0-1.0)
MAINTAINED: MARK(target_player_id, tightness:LOOSE|TIGHT), INTERCEPT(aggressive:bool)

## Field
x=-55 to +55, y=-35 to +35. Our goal x=-55. Opponent goal x=+55.

## Response
[{{"commandType":"PASS","playerId":{MY_PLAYER_ID},"parameters":{{"target_player_id":3,"type":"THROUGH"}},"duration":0}}]
Return ONLY the JSON array, no other text."""

fallback_commands = build_fallback(MID_CONFIG)
agent = create_agent(SYSTEM_PROMPT, model_id="us.amazon.nova-pro-v1:0")
create_invoke_handler(app, agent, MY_PLAYER_ID, POSITION_LABEL, fallback_commands, fallback_cfg=MID_CONFIG)

if __name__ == "__main__":
    app.run()
